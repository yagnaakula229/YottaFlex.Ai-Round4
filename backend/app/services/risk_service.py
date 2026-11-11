from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import and_, or_, select
from sqlalchemy.orm import Session, joinedload

from app.models import Alert, AuditEvent, RiskRule, Transaction, TransferLink
from app.services.identifiers import next_yearly_identifier
from app.services.link_analysis import analyze_account_links
from app.services.risk_engine import (
    EvaluationContext,
    MAX_RISK_SCORE_BPS,
    RuleDefinition,
    aggregate_score,
    evaluate_transaction,
    priority_for_score,
    utc_now,
)

DEFAULT_RULES = (
    ("velocity_spike", "High transaction velocity", 2500, {"window_minutes": 60, "minimum_count": 5}),
    ("high_value", "Unusual transaction amount", 3000, {"threshold_minor": 250000}),
    ("new_device", "New-device activity", 2500, {}),
    ("dormant_reactivation", "Dormant account reactivation", 3500, {"dormant_days": 90}),
    ("circular_transfer", "Circular transfers", 5000, {"minimum_accounts": 3, "lookback_days": 30}),
    ("linked_suspicious", "Linked suspicious transactions", 3000, {"minimum_related_alerts": 1, "lookback_days": 30}),
)
SYNTHETIC_ANALYST_ID = "analyst-demo-001"


def ensure_default_rules(session: Session, at: datetime | None = None) -> None:
    existing = session.scalars(select(RiskRule)).all()
    latest_by_key: dict[str, int] = {}
    active_keys = {rule.rule_key for rule in existing if rule.status == "active"}
    for rule in existing:
        latest_by_key[rule.rule_key] = max(latest_by_key.get(rule.rule_key, 0), rule.version)
    now = at or utc_now()
    for key, name, contribution, parameters in DEFAULT_RULES:
        if key in active_keys:
            continue
        version = latest_by_key.get(key, 0) + 1
        rule = RiskRule(
            rule_id=f"RUL-{key}-V{version:02d}",
            rule_key=key,
            version=version,
            name=name,
            description=f"Deterministic explainable rule: {name.lower()}.",
            status="active",
            parameters_json=parameters,
            default_score_contribution_bps=contribution,
            effective_at=now,
            created_at=now,
        )
        session.add(rule)
    session.flush()


def _rule_definitions(session: Session) -> list[RuleDefinition]:
    active_rules = session.scalars(
        select(RiskRule).where(RiskRule.status == "active").order_by(RiskRule.rule_key, RiskRule.version)
    ).all()
    latest_by_key: dict[str, RiskRule] = {}
    for rule in active_rules:
        current = latest_by_key.get(rule.rule_key)
        if current is None or rule.version > current.version:
            latest_by_key[rule.rule_key] = rule
    return [
        RuleDefinition(
            rule_id=rule.rule_id,
            rule_key=rule.rule_key,
            version=rule.version,
            parameters=rule.parameters_json,
            contribution_bps=rule.default_score_contribution_bps,
        )
        for rule in latest_by_key.values()
    ]


def _evaluation_context(
    session: Session,
    transaction: Transaction,
    rules: list[RuleDefinition],
) -> EvaluationContext:
    start = transaction.transaction_at - timedelta(days=366)
    prior = session.scalars(
        select(Transaction)
        .where(
            Transaction.account_id == transaction.account_id,
            Transaction.status == "posted",
            Transaction.transaction_at >= start,
            Transaction.transaction_at < transaction.transaction_at,
        )
        .order_by(Transaction.transaction_at.desc())
        .limit(100)
    ).all()
    prior_activity_at = session.scalar(
        select(Transaction.transaction_at)
        .where(
            Transaction.account_id == transaction.account_id,
            Transaction.status == "posted",
            Transaction.transaction_at < transaction.transaction_at,
        )
        .order_by(Transaction.transaction_at.desc())
        .limit(1)
    )
    device_is_new = False
    if transaction.device_id:
        device_is_new = (
            session.scalar(
                select(Transaction.transaction_id)
                .where(
                    Transaction.account_id == transaction.account_id,
                    Transaction.device_id == transaction.device_id,
                    Transaction.status == "posted",
                    Transaction.transaction_at < transaction.transaction_at,
                )
                .limit(1)
            )
            is None
        )

    rules_by_key = {rule.rule_key: rule for rule in rules}
    circular_rule = rules_by_key.get("circular_transfer")
    linked_rule = rules_by_key.get("linked_suspicious")
    transfer_lookback_days = int(
        circular_rule.parameters.get("lookback_days", 30) if circular_rule else 30
    )
    linked_lookback_days = int(
        linked_rule.parameters.get("lookback_days", 30) if linked_rule else 30
    )
    transfer_cutoff = transaction.transaction_at - timedelta(days=transfer_lookback_days)
    transfer_links = session.scalars(
        select(TransferLink).where(
            TransferLink.status == "reconciled",
            or_(
                and_(
                    TransferLink.initiated_at >= transfer_cutoff,
                    TransferLink.initiated_at <= transaction.transaction_at,
                ),
                TransferLink.source_transaction_id == transaction.transaction_id,
                TransferLink.destination_transaction_id == transaction.transaction_id,
            ),
        )
    ).all()

    links = analyze_account_links(
        session,
        transaction.account_id,
        as_of=transaction.transaction_at,
        lookback_days=linked_lookback_days,
    )
    related_account_ids = {transaction.account_id}
    related_account_ids.update(item["account_id"] for item in links["linked_accounts"])
    cutoff = transaction.transaction_at - timedelta(days=linked_lookback_days)
    rows = session.execute(
        select(Alert, Transaction.transaction_id, Transaction.account_id)
        .join(Transaction, Alert.triggering_transaction_id == Transaction.transaction_id)
        .where(
            Transaction.account_id.in_(related_account_ids),
            Transaction.transaction_at >= cutoff,
            Transaction.transaction_at < transaction.transaction_at,
        )
        .order_by(Transaction.transaction_at.desc())
        .limit(50)
    ).all()
    related_alerts = []
    for alert, related_transaction_id, related_account_id in rows:
        if alert.evidence_json.get("source") != "risk_engine":
            continue
        related_alerts.append(
            {
                "alert_id": alert.alert_id,
                "transaction_id": related_transaction_id,
                "account_id": related_account_id,
                "rule_id": alert.rule_id,
                "priority": alert.priority,
                "relationship": "same_account" if related_account_id == transaction.account_id else "linked_account",
            }
        )
    return EvaluationContext(
        prior_transactions=prior,
        prior_activity_at=prior_activity_at,
        device_is_new=device_is_new,
        transfers=transfer_links,
        related_alerts=related_alerts,
        account_status_at_posting=transaction.account_status_at_posting,
    )


def _next_alert_id(session: Session, year: int) -> str:
    return next_yearly_identifier(session, Alert, "alert_id", "ALT", year)


def evaluate_transactions(
    session: Session,
    *,
    transaction_id: str | None = None,
    limit: int = 500,
    after_transaction_at: datetime | None = None,
    after_transaction_id: str | None = None,
    evaluated_at: datetime | None = None,
) -> dict[str, Any]:
    event_time = evaluated_at or utc_now()
    ensure_default_rules(session, at=event_time)
    rules = _rule_definitions(session)
    statement = select(Transaction).where(Transaction.status == "posted")
    if transaction_id:
        statement = statement.where(Transaction.transaction_id == transaction_id)
    elif after_transaction_at is not None and after_transaction_id is not None:
        statement = statement.where(
            or_(
                Transaction.transaction_at > after_transaction_at,
                and_(
                    Transaction.transaction_at == after_transaction_at,
                    Transaction.transaction_id > after_transaction_id,
                ),
            )
        )
    statement = statement.order_by(Transaction.transaction_at, Transaction.transaction_id).limit(limit + 1)
    result_rows = session.scalars(statement).all()
    has_more = len(result_rows) > limit
    transactions = result_rows[:limit]
    evaluated = 0
    created_alerts = 0
    triggered = 0

    for transaction in transactions:
        findings = evaluate_transaction(
            transaction,
            rules,
            _evaluation_context(session, transaction, rules),
            evaluated_at=event_time,
        )
        evaluated += 1
        if not findings:
            continue
        triggered += len(findings)
        existing_alerts = session.scalars(
            select(Alert)
            .options(joinedload(Alert.rule))
            .where(Alert.triggering_transaction_id == transaction.transaction_id)
        ).all()
        engine_alerts = [
            alert for alert in existing_alerts if alert.evidence_json.get("source") == "risk_engine"
        ]
        existing_by_rule = {alert.rule_id: alert for alert in engine_alerts}
        new_alert_rows: list[Alert] = []
        for finding in findings:
            if finding.rule_id in existing_by_rule:
                continue
            alert = Alert(
                alert_id=_next_alert_id(session, transaction.transaction_at.year),
                rule_id=finding.rule_id,
                triggering_transaction_id=transaction.transaction_id,
                status="new",
                priority="P4",
                score_contribution_bps=finding.contribution_bps,
                evidence_json={
                    "schema_version": 1,
                    "source": "risk_engine",
                    "rule_key": finding.rule_key,
                    "rule_version": finding.rule_version,
                    "transaction_id": transaction.transaction_id,
                    "explanation": finding.explanation,
                    "evidence": finding.evidence,
                    "evaluated_at": finding.evaluated_at.isoformat(),
                },
                detected_at=finding.evaluated_at,
                created_at=finding.evaluated_at,
            )
            session.add(alert)
            session.flush()
            engine_alerts.append(alert)
            new_alert_rows.append(alert)
            created_alerts += 1

        score = aggregate_score([alert.score_contribution_bps for alert in engine_alerts])
        priority = priority_for_score(score)
        for alert in engine_alerts:
            previous_priority = alert.priority
            alert.priority = priority
            evidence = dict(alert.evidence_json)
            evidence["aggregate_score_bps"] = score
            alert.evidence_json = evidence
            if previous_priority != priority:
                session.add(
                    AuditEvent(
                        audit_event_id=next_yearly_identifier(
                            session, AuditEvent, "audit_event_id", "AUD", transaction.transaction_at.year
                        ),
                        event_type="alert.priority_changed",
                        entity_type="alert",
                        entity_id=alert.alert_id,
                        actor_type="system",
                        actor_id="system-risktrace",
                        event_at=event_time,
                        payload_json={
                            "from_priority": previous_priority,
                            "to_priority": priority,
                            "aggregate_score_bps": score,
                        },
                    )
                )
        for alert in new_alert_rows:
            session.add(
                AuditEvent(
                    audit_event_id=next_yearly_identifier(
                        session, AuditEvent, "audit_event_id", "AUD", transaction.transaction_at.year
                    ),
                    event_type="alert.created",
                    entity_type="alert",
                    entity_id=alert.alert_id,
                    actor_type="system",
                    actor_id="system-risktrace",
                    event_at=alert.detected_at,
                    payload_json={
                        "rule_id": alert.rule_id,
                        "transaction_id": transaction.transaction_id,
                        "score_contribution_bps": alert.score_contribution_bps,
                        "aggregate_score_bps": score,
                        "priority": priority,
                    },
                )
            )
    session.commit()
    return {
        "transactions_evaluated": evaluated,
        "findings": triggered,
        "alerts_created": created_alerts,
        "rule_count": len(rules),
        "next_cursor": (
            {
                "after_transaction_at": transactions[-1].transaction_at.isoformat(),
                "after_transaction_id": transactions[-1].transaction_id,
            }
            if has_more and transactions
            else None
        ),
    }


def alert_aggregate_score(session: Session, alert: Alert) -> int:
    rows = session.execute(
        select(Alert.score_contribution_bps, Alert.evidence_json).where(
            Alert.triggering_transaction_id == alert.triggering_transaction_id
        )
    ).all()
    source = alert.evidence_json.get("source", "legacy")
    return aggregate_score(
        [
            contribution
            for contribution, evidence in rows
            if evidence.get("source", "legacy") == source
        ]
    )


def alert_aggregate_scores(
    session: Session, transaction_ids: set[str]
) -> dict[tuple[str, str], int]:
    if not transaction_ids:
        return {}
    rows = session.execute(
        select(
            Alert.triggering_transaction_id,
            Alert.score_contribution_bps,
            Alert.evidence_json,
        )
        .where(Alert.triggering_transaction_id.in_(transaction_ids))
    ).all()
    totals: dict[tuple[str, str], int] = {}
    for transaction_id, contribution, evidence in rows:
        key = (transaction_id, evidence.get("source", "legacy"))
        totals[key] = min(MAX_RISK_SCORE_BPS, totals.get(key, 0) + contribution)
    return totals


def alert_to_read(
    session: Session,
    alert: Alert,
    aggregate_score_bps: int | None = None,
) -> dict[str, Any]:
    evidence = alert.evidence_json
    rule = alert.rule
    evaluated_at = evidence.get("evaluated_at")
    if isinstance(evaluated_at, str):
        from datetime import datetime

        evaluated_at = datetime.fromisoformat(evaluated_at)
    return {
        "alert_id": alert.alert_id,
        "rule_id": alert.rule_id,
        "rule_key": rule.rule_key,
        "rule_version": rule.version,
        "triggering_transaction_id": alert.triggering_transaction_id,
        "status": alert.status,
        "priority": alert.priority,
        "score_contribution_bps": alert.score_contribution_bps,
        "aggregate_score_bps": (
            aggregate_score_bps
            if aggregate_score_bps is not None
            else alert_aggregate_score(session, alert)
        ),
        "explanation": evidence.get("explanation", evidence.get("summary", rule.description)),
        "evidence": evidence.get("evidence", evidence),
        "evaluated_at": evaluated_at or alert.detected_at,
        "detected_at": alert.detected_at,
    }

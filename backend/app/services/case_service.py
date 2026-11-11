from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import and_, func, or_, select
from sqlalchemy.orm import Session, joinedload

from app.models import Alert, AnalystAction, AuditEvent, Case, CaseAlert, Transaction
from app.services.identifiers import next_yearly_identifier
from app.services.link_analysis import analyze_account_links
from app.services.risk_service import (
    SYNTHETIC_ANALYST_ID,
    alert_aggregate_scores,
    alert_to_read,
)
from app.services.risk_engine import utc_now

PRIORITY_ORDER = {"P1": 0, "P2": 1, "P3": 2, "P4": 3}
CASE_TRANSITIONS = {
    "open": {"in_review", "escalated", "resolved", "closed"},
    "in_review": {"escalated", "resolved", "closed"},
    "escalated": {"in_review", "resolved", "closed"},
    "resolved": {"in_review"},
    "closed": {"in_review"},
}
ALERT_TRANSITIONS = {
    "new": {"acknowledged", "in_review", "escalated", "closed"},
    "acknowledged": {"in_review", "escalated", "resolved", "closed"},
    "in_review": {"escalated", "resolved", "closed"},
    "escalated": {"in_review", "resolved", "closed"},
    "resolved": {"in_review"},
    "closed": {"in_review"},
}
ACTIVE_CASE_STATUSES = {"open", "in_review", "escalated"}
ALERT_STATUS_BY_CASE = {
    "in_review": "in_review",
    "escalated": "escalated",
    "resolved": "resolved",
    "closed": "closed",
}


def _id(session: Session, model, attribute: str, prefix: str, year: int) -> str:
    return next_yearly_identifier(session, model, attribute, prefix, year)


def list_cases(
    session: Session,
    *,
    status: str | None = None,
    priority: str | None = None,
    limit: int = 100,
    offset: int = 0,
) -> tuple[list[dict[str, Any]], int]:
    statement = select(Case)
    count_statement = select(func.count(Case.case_id))
    conditions = []
    if status:
        conditions.append(Case.status == status)
    if priority:
        conditions.append(Case.priority == priority)
    if conditions:
        statement = statement.where(*conditions)
        count_statement = count_statement.where(*conditions)
    cases = session.scalars(
        statement.order_by(Case.updated_at.desc(), Case.case_id).limit(limit).offset(offset)
    ).all()
    total = session.scalar(count_statement) or 0
    linked_counts = {}
    if cases:
        linked_counts = dict(
            session.execute(
                select(CaseAlert.case_id, func.count(CaseAlert.case_alert_id))
                .where(
                    CaseAlert.case_id.in_([case.case_id for case in cases]),
                    CaseAlert.status == "linked",
                )
                .group_by(CaseAlert.case_id)
            ).all()
        )
    result = []
    for case in cases:
        count = linked_counts.get(case.case_id, 0)
        result.append(
            {
                "case_id": case.case_id,
                "title": case.title,
                "status": case.status,
                "priority": case.priority,
                "alert_count": count,
                "created_at": case.created_at,
                "updated_at": case.updated_at,
            }
        )
    return result, total


def get_case_detail(session: Session, case_id: str) -> dict[str, Any] | None:
    case = session.get(Case, case_id)
    if case is None:
        return None
    links = session.scalars(
        select(CaseAlert)
        .options(joinedload(CaseAlert.alert).joinedload(Alert.rule))
        .where(CaseAlert.case_id == case_id, CaseAlert.status == "linked")
        .order_by(CaseAlert.linked_at, CaseAlert.alert_id)
    ).all()
    actions = session.scalars(
        select(AnalystAction)
        .where(AnalystAction.case_id == case_id)
        .order_by(AnalystAction.action_at, AnalystAction.action_id)
    ).all()
    aggregate_scores = alert_aggregate_scores(
        session, {link.alert.triggering_transaction_id for link in links}
    )
    alert_ids = {link.alert_id for link in links}
    audit_condition = and_(AuditEvent.entity_type == "case", AuditEvent.entity_id == case_id)
    if alert_ids:
        audit_condition = or_(
            audit_condition,
            and_(AuditEvent.entity_type == "alert", AuditEvent.entity_id.in_(alert_ids)),
        )
    audit_events = session.scalars(
        select(AuditEvent)
        .where(audit_condition)
        .order_by(AuditEvent.event_at, AuditEvent.audit_event_id)
    ).all()
    return {
        "case_id": case.case_id,
        "title": case.title,
        "status": case.status,
        "priority": case.priority,
        "alert_count": len(links),
        "created_at": case.created_at,
        "updated_at": case.updated_at,
        "alerts": [
            alert_to_read(
                session,
                link.alert,
                aggregate_scores.get(
                    (
                        link.alert.triggering_transaction_id,
                        link.alert.evidence_json.get("source", "legacy"),
                    ),
                    0,
                ),
            )
            for link in links
        ],
        "actions": [
            {
                "action_id": action.action_id,
                "action_type": action.action_type,
                "disposition": action.disposition,
                "alert_id": action.alert_id,
                "action_at": action.action_at,
                "actor_id": action.actor_id,
                "note": action.note,
                "details_json": action.details_json,
            }
            for action in actions
        ],
        "audit_events": [
            {
                "audit_event_id": event.audit_event_id,
                "event_type": event.event_type,
                "entity_type": event.entity_type,
                "entity_id": event.entity_id,
                "actor_type": event.actor_type,
                "actor_id": event.actor_id,
                "event_at": event.event_at,
                "payload_json": event.payload_json,
            }
            for event in audit_events
        ],
    }


def _account_relationship_reasons(
    session: Session,
    first_account_id: str,
    second_account_id: str,
    as_of: datetime,
) -> list[dict[str, Any]]:
    if first_account_id == second_account_id:
        return [{"type": "same_account"}]

    reasons = []
    for source_account_id, related_account_id in (
        (first_account_id, second_account_id),
        (second_account_id, first_account_id),
    ):
        analysis = analyze_account_links(session, source_account_id, as_of=as_of)
        related_account = next(
            (
                account
                for account in analysis["linked_accounts"]
                if account["account_id"] == related_account_id
            ),
            None,
        )
        if related_account:
            reasons.extend(related_account["reasons"])
    return sorted(reasons, key=lambda reason: (reason["type"], str(reason)))


def _attach_singleton_to_active_case(
    session: Session,
    alert: Alert,
    account_id: str,
    transaction_at: datetime,
    at: datetime,
) -> str | None:
    linked_rows = session.execute(
        select(Case, Alert.alert_id, Transaction.account_id, Transaction.transaction_at)
        .join(CaseAlert, CaseAlert.case_id == Case.case_id)
        .join(Alert, Alert.alert_id == CaseAlert.alert_id)
        .join(Transaction, Transaction.transaction_id == Alert.triggering_transaction_id)
        .where(
            Case.status.in_(ACTIVE_CASE_STATUSES),
            CaseAlert.status == "linked",
        )
        .order_by(Case.created_at, Case.case_id, Alert.alert_id)
    ).all()

    matching_cases: dict[str, tuple[Case, dict[str, Any]]] = {}
    for case, _, linked_account_id, linked_transaction_at in linked_rows:
        as_of = max(transaction_at, linked_transaction_at)
        reasons = _account_relationship_reasons(
            session, account_id, linked_account_id, as_of
        )
        if reasons and case.case_id not in matching_cases:
            matching_cases[case.case_id] = (case, reasons[0])

    if not matching_cases:
        return None

    case, relationship_reason = min(
        matching_cases.values(),
        key=lambda match: (match[0].created_at, match[0].case_id),
    )
    existing_link = session.scalar(
        select(CaseAlert).where(
            CaseAlert.case_id == case.case_id,
            CaseAlert.alert_id == alert.alert_id,
        )
    )
    if existing_link is None:
        session.add(
            CaseAlert(
                case_alert_id=_id(session, CaseAlert, "case_alert_id", "CAL", at.year),
                case_id=case.case_id,
                alert_id=alert.alert_id,
                linked_at=at,
                linked_by_actor_id="system-risktrace",
                link_reason="rule_correlation",
                status="linked",
            )
        )
    elif existing_link.status == "unlinked":
        existing_link.linked_at = at
        existing_link.linked_by_actor_id = "system-risktrace"
        existing_link.link_reason = "rule_correlation"
        existing_link.status = "linked"
        existing_link.unlinked_at = None

    session.flush()
    linked_priorities = session.scalars(
        select(Alert.priority)
        .join(CaseAlert, CaseAlert.alert_id == Alert.alert_id)
        .where(CaseAlert.case_id == case.case_id, CaseAlert.status == "linked")
    ).all()
    case.priority = min(linked_priorities, key=PRIORITY_ORDER.__getitem__)
    case.updated_at = max(at, case.updated_at)
    session.add(
        AuditEvent(
            audit_event_id=_id(session, AuditEvent, "audit_event_id", "AUD", at.year),
            event_type="case.alert_attached",
            entity_type="case",
            entity_id=case.case_id,
            actor_type="system",
            actor_id="system-risktrace",
            event_at=at,
            payload_json={
                "case_id": case.case_id,
                "alert_id": alert.alert_id,
                "relationship_reason": relationship_reason["type"],
                "relationship_evidence": relationship_reason,
            },
        )
    )
    return case.case_id


def group_related_alerts(
    session: Session,
    limit: int = 1000,
    at: datetime | None = None,
) -> dict[str, Any]:
    alert_rows = session.execute(
        select(Alert, Transaction.account_id, Transaction.transaction_at)
        .join(Transaction, Alert.triggering_transaction_id == Transaction.transaction_id)
        .where(Alert.status.in_(("new", "acknowledged", "in_review", "escalated")))
        .order_by(Transaction.transaction_at, Alert.alert_id)
        .limit(limit)
    ).all()
    alerts = [row[0] for row in alert_rows]
    if not alerts:
        return {
            "cases_created": 0,
            "case_ids": [],
            "attached_case_ids": [],
            "alert_count": 0,
        }
    existing_links = set(session.scalars(
        select(CaseAlert.alert_id)
        .join(Case, CaseAlert.case_id == Case.case_id)
        .where(CaseAlert.status == "linked", Case.status.in_(ACTIVE_CASE_STATUSES))
    ).all())
    eligible = [alert for alert in alerts if alert.alert_id not in existing_links]
    if len(eligible) < 2:
        attached_case_ids = []
        if len(eligible) == 1:
            singleton = eligible[0]
            row = next(row for row in alert_rows if row[0].alert_id == singleton.alert_id)
            now = at or utc_now()
            case_id = _attach_singleton_to_active_case(
                session,
                singleton,
                row[1],
                row[2],
                now,
            )
            if case_id:
                session.commit()
                attached_case_ids.append(case_id)
        return {
            "cases_created": 0,
            "case_ids": [],
            "attached_case_ids": attached_case_ids,
            "alert_count": len(eligible),
        }

    eligible_ids = {alert.alert_id for alert in eligible}
    account_for_alert = {
        alert.alert_id: account_id
        for alert, account_id, _ in alert_rows
        if alert.alert_id in eligible_ids
    }
    transaction_time_for_alert = {
        alert.alert_id: transaction_at
        for alert, _, transaction_at in alert_rows
        if alert.alert_id in eligible_ids
    }
    linked_accounts: dict[str, set[str]] = {}
    as_of_by_account: dict[str, datetime] = {}
    for alert in eligible:
        account_id = account_for_alert[alert.alert_id]
        as_of_by_account[account_id] = max(
            as_of_by_account.get(account_id, transaction_time_for_alert[alert.alert_id]),
            transaction_time_for_alert[alert.alert_id],
        )
    for account_id in set(account_for_alert.values()):
        analysis = analyze_account_links(
            session, account_id, as_of=as_of_by_account[account_id]
        )
        linked_accounts[account_id] = {row["account_id"] for row in analysis["linked_accounts"]}

    adjacency = {alert.alert_id: set() for alert in eligible}
    for index, first in enumerate(eligible):
        first_account = account_for_alert[first.alert_id]
        for second in eligible[index + 1 :]:
            second_account = account_for_alert[second.alert_id]
            if (
                first_account == second_account
                or second_account in linked_accounts.get(first_account, set())
                or first_account in linked_accounts.get(second_account, set())
            ):
                adjacency[first.alert_id].add(second.alert_id)
                adjacency[second.alert_id].add(first.alert_id)

    by_id = {alert.alert_id: alert for alert in eligible}
    components: list[list[Alert]] = []
    visited: set[str] = set()
    for alert_id in sorted(adjacency):
        if alert_id in visited:
            continue
        stack = [alert_id]
        component: list[Alert] = []
        visited.add(alert_id)
        while stack:
            current = stack.pop()
            component.append(by_id[current])
            for neighbor in adjacency[current] - visited:
                visited.add(neighbor)
                stack.append(neighbor)
        if len(component) >= 2:
            components.append(component)

    now = at or utc_now()
    created_ids = []
    for component in components:
        ordered = sorted(component, key=lambda alert: alert.alert_id)
        year = min(
            transaction_time_for_alert[alert.alert_id].year
            for alert in ordered
        )
        case_id = _id(session, Case, "case_id", "CASE", year)
        priority = min((alert.priority for alert in ordered), key=PRIORITY_ORDER.__getitem__)
        case = Case(
            case_id=case_id,
            title=f"Correlated alert review ({len(ordered)} alerts)",
            status="open",
            priority=priority,
            created_at=now,
            updated_at=now,
            created_by_actor_id="system-risktrace",
        )
        session.add(case)
        session.flush()
        for alert in ordered:
            session.add(
                CaseAlert(
                    case_alert_id=_id(session, CaseAlert, "case_alert_id", "CAL", year),
                    case_id=case_id,
                    alert_id=alert.alert_id,
                    linked_at=now,
                    linked_by_actor_id="system-risktrace",
                    link_reason="rule_correlation",
                    status="linked",
                )
            )
        session.add(
            AuditEvent(
                audit_event_id=_id(session, AuditEvent, "audit_event_id", "AUD", year),
                event_type="case.grouped",
                entity_type="case",
                entity_id=case_id,
                actor_type="system",
                actor_id="system-risktrace",
                event_at=now,
                payload_json={"alert_ids": [alert.alert_id for alert in ordered]},
            )
        )
        created_ids.append(case_id)
    session.commit()
    return {
        "cases_created": len(created_ids),
        "case_ids": created_ids,
        "attached_case_ids": [],
        "alert_count": sum(
            sum(alert.alert_id in component_ids for alert in eligible)
            for component_ids in [
                {alert.alert_id for alert in component}
                for component in components
            ]
        ),
    }


def _transition_case(case: Case, target_status: str, at: datetime) -> None:
    if target_status not in CASE_TRANSITIONS:
        raise ValueError(f"Unsupported case status: {target_status}")
    if target_status == case.status:
        raise ValueError(f"Case is already {target_status}.")
    if target_status not in CASE_TRANSITIONS[case.status]:
        raise ValueError(f"Invalid case transition: {case.status} -> {target_status}.")
    case.status = target_status
    case.updated_at = at
    if target_status == "resolved":
        case.resolved_at = at
        case.closed_at = None
    elif target_status == "closed":
        case.closed_at = at
    elif target_status == "in_review":
        case.resolved_at = None
        case.closed_at = None


def _reject_analyst_action(
    session: Session,
    case_id: str,
    payload: dict[str, Any],
    reason: str,
    at: datetime,
) -> None:
    session.add(
        AuditEvent(
            audit_event_id=_id(session, AuditEvent, "audit_event_id", "AUD", at.year),
            event_type="analyst.action_rejected",
            entity_type="case",
            entity_id=case_id,
            actor_type="analyst",
            actor_id=SYNTHETIC_ANALYST_ID,
            event_at=at,
            payload_json={
                "action_type": payload.get("action_type"),
                "alert_id": payload.get("alert_id"),
                "reason": reason,
            },
        )
    )
    session.commit()
    raise ValueError(reason)


def record_analyst_action(
    session: Session,
    case_id: str,
    payload: dict[str, Any],
    at: datetime | None = None,
) -> AnalystAction:
    case = session.get(Case, case_id)
    if case is None:
        raise LookupError(f"Case {case_id} was not found.")
    now = at or utc_now()
    idempotency_key = payload.get("idempotency_key")
    if idempotency_key:
        existing = session.scalar(
            select(AnalystAction).where(AnalystAction.idempotency_key == idempotency_key)
        )
        if existing:
            if existing.case_id != case_id:
                _reject_analyst_action(
                    session, case_id, payload, "Idempotency key already belongs to a different case.", now
                )
            if (
                existing.action_type != payload["action_type"]
                or existing.alert_id != payload.get("alert_id")
                or existing.disposition != payload.get("disposition")
                or existing.note != payload.get("note")
                or (
                    payload["action_type"] == "status_changed"
                    and existing.details_json.get("target_status") != payload.get("target_status")
                )
            ):
                _reject_analyst_action(
                    session, case_id, payload, "Idempotency key was already used with a different action.", now
                )
            return existing

    action_type = payload["action_type"]
    alert = None
    alert_id = payload.get("alert_id")
    if alert_id:
        link = session.scalar(
            select(CaseAlert).where(
                CaseAlert.case_id == case_id,
                CaseAlert.alert_id == alert_id,
                CaseAlert.status == "linked",
            )
        )
        if link is None:
            _reject_analyst_action(
                session, case_id, payload, "The alert is not currently linked to this case.", now
            )
        alert = session.get(Alert, alert_id)
        if alert is None:
            raise LookupError(f"Alert {alert_id} was not found.")

    if alert and (now < alert.detected_at or now < link.linked_at):
        _reject_analyst_action(
            session,
            case_id,
            payload,
            "Analyst action cannot precede the alert or case-alert association.",
            now,
        )
    latest_action = session.scalar(
        select(AnalystAction)
        .where(AnalystAction.case_id == case_id)
        .order_by(AnalystAction.action_at.desc(), AnalystAction.action_id.desc())
        .limit(1)
    )
    if latest_action and now < latest_action.action_at:
        _reject_analyst_action(
            session, case_id, payload, "Analyst action cannot precede the previous case action.", now
        )
    if case.status in {"resolved", "closed"} and action_type not in {"case_reopened", "note_added"}:
        _reject_analyst_action(
            session,
            case_id,
            payload,
            "Resolved or closed cases must be reopened before further disposition.",
            now,
        )

    target_status = None
    if action_type == "review_started":
        target_status = "in_review"
    elif action_type == "disposition_recorded":
        if case.status != "in_review":
            _reject_analyst_action(
                session,
                case_id,
                payload,
                "A case must be in_review before an analyst records a disposition.",
                now,
            )
        target_status = "escalated" if payload.get("disposition") == "referred" else "resolved"
    elif action_type == "escalated":
        target_status = "escalated"
    elif action_type == "status_changed":
        target_status = payload.get("target_status")
    elif action_type == "case_closed":
        target_status = "closed"
    elif action_type == "case_reopened":
        if case.status not in {"resolved", "closed"}:
            _reject_analyst_action(
                session, case_id, payload, "Only resolved or closed cases can be reopened.", now
            )
        target_status = "in_review"
    if now < case.created_at:
        _reject_analyst_action(
            session, case_id, payload, "Analyst action cannot precede case creation.", now
        )
    linked_alerts = []
    if target_status in ALERT_STATUS_BY_CASE:
        linked_alerts = [
            session.get(Alert, case_alert.alert_id)
            for case_alert in session.scalars(
                select(CaseAlert).where(CaseAlert.case_id == case_id, CaseAlert.status == "linked")
            )
        ]
        next_alert_status = ALERT_STATUS_BY_CASE[target_status]
        invalid_alerts = [
            alert
            for alert in linked_alerts
            if alert and alert.status != next_alert_status
            and next_alert_status not in ALERT_TRANSITIONS[alert.status]
        ]
        if invalid_alerts:
            _reject_analyst_action(
                session,
                case_id,
                payload,
                f"Invalid alert lifecycle transition for {invalid_alerts[0].alert_id}.",
                now,
            )
    if target_status:
        try:
            _transition_case(case, target_status, now)
        except ValueError as exc:
            _reject_analyst_action(session, case_id, payload, str(exc), now)

    action_year = now.year
    action = AnalystAction(
        action_id=_id(session, AnalystAction, "action_id", "ACT", action_year),
        case_id=case_id,
        alert_id=alert_id,
        action_type=action_type,
        disposition=payload.get("disposition"),
        actor_id=SYNTHETIC_ANALYST_ID,
        action_at=now,
        note=payload.get("note"),
        details_json={"target_status": target_status} if target_status else {},
        idempotency_key=idempotency_key,
    )
    session.add(action)

    if target_status in ALERT_STATUS_BY_CASE:
        for linked_alert in linked_alerts:
            if linked_alert:
                previous_status = linked_alert.status
                linked_alert.status = ALERT_STATUS_BY_CASE[target_status]
                session.add(
                    AuditEvent(
                        audit_event_id=_id(session, AuditEvent, "audit_event_id", "AUD", action_year),
                        event_type="alert.status_changed",
                        entity_type="alert",
                        entity_id=linked_alert.alert_id,
                        actor_type="analyst",
                        actor_id=SYNTHETIC_ANALYST_ID,
                        event_at=now,
                        payload_json={
                            "case_id": case_id,
                            "from_status": previous_status,
                            "to_status": linked_alert.status,
                            "action_id": action.action_id,
                        },
                    )
                )
    audit = AuditEvent(
        audit_event_id=_id(session, AuditEvent, "audit_event_id", "AUD", action_year),
        event_type="analyst.action_recorded",
        entity_type="case",
        entity_id=case_id,
        actor_type="analyst",
        actor_id=SYNTHETIC_ANALYST_ID,
        event_at=now,
        payload_json={
            "action_id": action.action_id,
            "action_type": action_type,
            "alert_id": alert_id,
            "disposition": payload.get("disposition"),
            "target_status": target_status,
        },
    )
    session.add(audit)
    session.commit()
    session.refresh(action)
    return action


def action_to_read(action: AnalystAction) -> dict[str, Any]:
    return {
        "action_id": action.action_id,
        "case_id": action.case_id,
        "alert_id": action.alert_id,
        "action_type": action.action_type,
        "disposition": action.disposition,
        "actor_id": action.actor_id,
        "action_at": action.action_at,
        "note": action.note,
        "details_json": action.details_json,
    }

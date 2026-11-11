from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Sequence

MAX_RISK_SCORE_BPS = 10_000
PRIORITY_THRESHOLDS_BPS = {"P1": 7_500, "P2": 5_000, "P3": 2_500}


@dataclass(frozen=True)
class RuleDefinition:
    rule_id: str
    rule_key: str
    version: int
    parameters: dict[str, Any]
    contribution_bps: int


@dataclass(frozen=True)
class RiskFinding:
    rule_id: str
    rule_key: str
    rule_version: int
    triggering_transaction_id: str
    contribution_bps: int
    evaluated_at: datetime
    explanation: str
    evidence: dict[str, Any]


@dataclass(frozen=True)
class EvaluationContext:
    prior_transactions: Sequence[Any] = ()
    prior_activity_at: datetime | None = None
    device_is_new: bool = False
    transfers: Sequence[Any] = ()
    related_alerts: Sequence[dict[str, Any]] = ()
    account_status_at_posting: str | None = None


def priority_for_score(
    score_bps: int,
    thresholds: dict[str, int] = PRIORITY_THRESHOLDS_BPS,
) -> str:
    if not 0 <= score_bps <= MAX_RISK_SCORE_BPS:
        raise ValueError(f"aggregate score must be between 0 and {MAX_RISK_SCORE_BPS} bps")
    if score_bps >= thresholds["P1"]:
        return "P1"
    if score_bps >= thresholds["P2"]:
        return "P2"
    if score_bps >= thresholds["P3"]:
        return "P3"
    return "P4"


def aggregate_score(
    contributions: Sequence[int],
    cap_bps: int = MAX_RISK_SCORE_BPS,
) -> int:
    if not 0 <= cap_bps <= MAX_RISK_SCORE_BPS or any(
        value < 0 or value > MAX_RISK_SCORE_BPS for value in contributions
    ):
        raise ValueError("rule contribution and aggregate cap must be valid basis-point values")
    return min(sum(contributions), cap_bps)


def _circular_transfer_evidence(
    transaction: Any,
    links: Sequence[Any],
    minimum_accounts: int,
    max_hops: int = 6,
) -> dict[str, Any] | None:
    matching = [
        link
        for link in links
        if transaction.transaction_id in (link.source_transaction_id, link.destination_transaction_id)
        and link.status == "reconciled"
    ]
    ordered_links = sorted(links, key=lambda link: link.transfer_id)
    for start in matching:
        start_edge = (start.source_account_id, start.destination_account_id)
        path: list[Any] = [start]

        def find_path(current: str, goal: str, visited: set[str], used: set[str]) -> bool:
            if current == goal and len(path) >= 2:
                return len(visited) >= minimum_accounts
            if len(path) >= max_hops:
                return False
            for link in ordered_links:
                if link.transfer_id in used or link.status != "reconciled":
                    continue
                if link.source_account_id != current:
                    continue
                next_account = link.destination_account_id
                if next_account != goal and next_account in visited:
                    continue
                path.append(link)
                if find_path(
                    next_account,
                    goal,
                    visited | {next_account},
                    used | {link.transfer_id},
                ):
                    return True
                path.pop()
            return False

        if find_path(start_edge[1], start_edge[0], set(start_edge), {start.transfer_id}):
            return {
                "account_path": [path[0].source_account_id]
                + [link.destination_account_id for link in path],
                "transfer_ids": [link.transfer_id for link in path],
            }
    return None


def _rule_evidence(rule: RuleDefinition, transaction: Any, context: EvaluationContext) -> tuple[str, dict[str, Any]] | None:
    amount_minor = max(transaction.debit_minor, transaction.credit_minor)
    if rule.rule_key == "velocity_spike":
        window_minutes = int(rule.parameters.get("window_minutes", 60))
        minimum_count = int(rule.parameters.get("minimum_count", 5))
        window_start = transaction.transaction_at - timedelta(minutes=window_minutes)
        count = 1 + sum(
            item.status == "posted"
            and item.transaction_id != transaction.transaction_id
            and window_start <= item.transaction_at < transaction.transaction_at
            for item in context.prior_transactions
        )
        if count >= minimum_count:
            return (
                f"{count} posted transactions occurred in a {window_minutes}-minute window.",
                {"window_minutes": window_minutes, "transaction_count": count, "minimum_count": minimum_count},
            )
    elif rule.rule_key == "new_device" and transaction.device_id and context.device_is_new:
        return (
            "This is the first observed use of the device for the account.",
            {"device_id": transaction.device_id, "account_id": transaction.account_id, "first_use": True},
        )
    elif rule.rule_key == "circular_transfer":
        minimum_accounts = int(rule.parameters.get("minimum_accounts", 3))
        circular = _circular_transfer_evidence(
            transaction,
            context.transfers,
            minimum_accounts,
            int(rule.parameters.get("max_hops", 6)),
        )
        if circular:
            return ("The transfer leg participates in a reconciled circular account path.", circular)
    elif rule.rule_key == "dormant_reactivation":
        dormant_days = int(rule.parameters.get("dormant_days", 90))
        gap_days = None
        if context.prior_activity_at is not None:
            gap_days = (transaction.transaction_at - context.prior_activity_at).total_seconds() / 86400
        explicitly_dormant = context.account_status_at_posting == "dormant"
        if explicitly_dormant or (gap_days is not None and gap_days >= dormant_days):
            return (
                "Activity resumed after a dormant period.",
                {
                    "dormant_days": dormant_days,
                    "days_since_prior_activity": round(gap_days, 2) if gap_days is not None else None,
                    "account_status_at_posting": context.account_status_at_posting,
                },
            )
    elif rule.rule_key == "high_value":
        threshold_minor = int(rule.parameters.get("threshold_minor", 250_000))
        if amount_minor >= threshold_minor:
            return (
                "The transaction amount meets or exceeds the configured unusual-amount threshold.",
                {"amount_minor": amount_minor, "threshold_minor": threshold_minor},
            )
    elif rule.rule_key == "linked_suspicious":
        minimum = int(rule.parameters.get("minimum_related_alerts", 1))
        if len(context.related_alerts) >= minimum:
            return (
                "The transaction is linked to a separate transaction with an existing risk alert.",
                {"related_alerts": list(context.related_alerts), "lookback_days": rule.parameters.get("lookback_days", 30)},
            )
    return None


def evaluate_transaction(
    transaction: Any,
    rules: Sequence[RuleDefinition],
    context: EvaluationContext | None = None,
    evaluated_at: datetime | None = None,
) -> list[RiskFinding]:
    if transaction.status != "posted":
        return []
    context = context or EvaluationContext()
    timestamp = evaluated_at or datetime.now(timezone.utc)
    findings: list[RiskFinding] = []
    for rule in sorted(rules, key=lambda item: (item.rule_key, item.version, item.rule_id)):
        matched = _rule_evidence(rule, transaction, context)
        if matched is None:
            continue
        explanation, evidence = matched
        findings.append(
            RiskFinding(
                rule_id=rule.rule_id,
                rule_key=rule.rule_key,
                rule_version=rule.version,
                triggering_transaction_id=transaction.transaction_id,
                contribution_bps=rule.contribution_bps,
                evaluated_at=timestamp,
                explanation=explanation,
                evidence=evidence,
            )
        )
    return findings


def utc_now() -> datetime:
    return datetime.now(timezone.utc)

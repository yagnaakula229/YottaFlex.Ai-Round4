from __future__ import annotations

from collections import Counter

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import Account, Alert, AnalystAction, Case, Transaction


def dashboard_summary(session: Session) -> dict:
    alert_rows = session.execute(
        select(Alert.priority, Transaction.account_id)
        .join(Transaction, Alert.triggering_transaction_id == Transaction.transaction_id)
    ).all()
    alerts_by_priority = {priority: 0 for priority in ("P1", "P2", "P3", "P4")}
    best_priority_by_account: dict[str, str] = {}
    priority_order = {"P1": 0, "P2": 1, "P3": 2, "P4": 3}
    for priority, account_id in alert_rows:
        alerts_by_priority[priority] += 1
        current = best_priority_by_account.get(account_id)
        if current is None or priority_order[priority] < priority_order[current]:
            best_priority_by_account[account_id] = priority

    account_risk_distribution = {priority: 0 for priority in ("P1", "P2", "P3", "P4")}
    account_risk_distribution["UNASSESSED"] = 0
    accounts = session.scalars(select(Account.account_id)).all()
    for account_id in accounts:
        account_risk_distribution[best_priority_by_account.get(account_id, "UNASSESSED")] += 1

    dispositions = Counter(
        session.scalars(
            select(AnalystAction.disposition).where(
                AnalystAction.action_type == "disposition_recorded",
                AnalystAction.disposition.is_not(None),
            )
        ).all()
    )
    latest_by_alert: dict[str, AnalystAction] = {}
    for action in session.scalars(
        select(AnalystAction)
        .where(
            AnalystAction.action_type == "disposition_recorded",
            AnalystAction.disposition.is_not(None),
            AnalystAction.alert_id.is_not(None),
        )
        .order_by(AnalystAction.action_at, AnalystAction.action_id)
    ):
        latest_by_alert[action.alert_id] = action
    alerts = session.scalars(select(Alert)).all()
    suspicious_transaction_ids = {
        alert.triggering_transaction_id
        for alert in alerts
        if latest_by_alert.get(alert.alert_id)
        and latest_by_alert[alert.alert_id].disposition == "suspicious"
    }

    return {
        "total_transactions": session.scalar(select(func.count(Transaction.transaction_id))) or 0,
        "total_alerts": session.scalar(select(func.count(Alert.alert_id))) or 0,
        "alerts_by_priority": alerts_by_priority,
        "open_cases": session.scalar(
            select(func.count(Case.case_id)).where(Case.status.in_(("open", "in_review", "escalated")))
        )
        or 0,
        "suspicious_transactions": len(suspicious_transaction_ids),
        "account_risk_distribution": account_risk_distribution,
        "analyst_dispositions": {key: dispositions.get(key, 0) for key in ("suspicious", "false_positive", "inconclusive", "referred")},
    }

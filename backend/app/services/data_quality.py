from collections import defaultdict
from typing import Any

from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from app.database.session import Base
from app.models import Account, Alert, AnalystAction, Case, CaseAlert, CustomerAccount, Transaction, TransferLink
from app.services.risk_engine import aggregate_score, priority_for_score

PRIORITY_ORDER = {"P1": 0, "P2": 1, "P3": 2, "P4": 3}


def validate_dataset(session: Session) -> dict[str, Any]:
    connection = session.connection()
    fk_errors = connection.execute(text("PRAGMA foreign_key_check")).all()
    if fk_errors:
        raise ValueError(f"SQLite foreign-key violations: {fk_errors[:5]}")

    counts: dict[str, int] = {}
    for table in Base.metadata.sorted_tables:
        pk = list(table.primary_key.columns)[0]
        total, distinct = session.execute(
            select(func.count(), func.count(func.distinct(pk))).select_from(table)
        ).one()
        if total != distinct:
            raise ValueError(f"duplicate primary key in {table.name}")
        counts[table.name] = total

    accounts = session.scalars(select(Account).order_by(Account.account_id)).all()
    ownership_by_account: dict[str, list[CustomerAccount]] = defaultdict(list)
    ownership_by_pair: dict[tuple[str, str], list[CustomerAccount]] = defaultdict(list)
    for ownership in session.scalars(
        select(CustomerAccount).order_by(
            CustomerAccount.customer_id, CustomerAccount.account_id, CustomerAccount.valid_from
        )
    ):
        ownership_by_account[ownership.account_id].append(ownership)
        ownership_by_pair[(ownership.customer_id, ownership.account_id)].append(ownership)
    for pair, intervals in ownership_by_pair.items():
        for previous, following in zip(intervals, intervals[1:]):
            if previous.valid_to is None or previous.valid_to > following.valid_from:
                raise ValueError(f"overlapping ownership intervals for {pair}")
    latest_activity = dict(
        session.execute(
            select(Transaction.account_id, func.max(Transaction.transaction_at))
            .where(Transaction.status == "posted")
            .group_by(Transaction.account_id)
        ).all()
    )
    unowned = []
    for account in accounts:
        ownership_anchor = max(account.opened_at, latest_activity.get(account.account_id, account.opened_at))
        if account.status != "closed" and not any(
            ownership.status == "active"
            and ownership.valid_from <= ownership_anchor
            and (ownership.valid_to is None or ownership.valid_to > ownership_anchor)
            for ownership in ownership_by_account[account.account_id]
        ):
            unowned.append(account.account_id)
    if unowned:
        raise ValueError(f"accounts without active ownership: {unowned[:5]}")

    ledger: dict[str, list[Transaction]] = defaultdict(list)
    for transaction in session.scalars(
        select(Transaction).where(Transaction.status == "posted").order_by(
            Transaction.account_id, Transaction.transaction_at, Transaction.transaction_id
        )
    ):
        ledger[transaction.account_id].append(transaction)

    account_by_id = {account.account_id: account for account in accounts}
    for reversal in session.scalars(
        select(Transaction).where(Transaction.reversal_of_transaction_id.is_not(None))
    ):
        original = session.get(Transaction, reversal.reversal_of_transaction_id)
        if (
            original is None
            or original.status != "posted"
            or reversal.status != "posted"
            or reversal.transaction_id == original.transaction_id
            or reversal.account_id != original.account_id
            or reversal.currency != original.currency
            or reversal.debit_minor != original.credit_minor
            or reversal.credit_minor != original.debit_minor
        ):
            raise ValueError(f"invalid reversal relationship for {reversal.transaction_id}")

    for account_id, entries in ledger.items():
        account = account_by_id[account_id]
        balance = account.opening_balance_minor
        for entry in entries:
            if entry.transaction_at < account.opened_at or (
                account.closed_at is not None and entry.transaction_at > account.closed_at
            ):
                raise ValueError(f"transaction outside account lifecycle: {entry.transaction_id}")
            if not any(
                ownership.status == "active"
                and ownership.valid_from <= entry.transaction_at
                and (ownership.valid_to is None or ownership.valid_to > entry.transaction_at)
                for ownership in ownership_by_account[account_id]
            ):
                raise ValueError(f"transaction without effective account ownership: {entry.transaction_id}")
            if entry.currency != account.currency or entry.currency != "USD":
                raise ValueError(f"currency mismatch on transaction {entry.transaction_id}")
            if (entry.debit_minor > 0) == (entry.credit_minor > 0):
                raise ValueError(f"invalid debit/credit direction on {entry.transaction_id}")
            if entry.opening_balance_minor != balance:
                raise ValueError(f"opening balance mismatch on {entry.transaction_id}")
            balance = balance - entry.debit_minor + entry.credit_minor
            if entry.closing_balance_minor != balance:
                raise ValueError(f"closing balance mismatch on {entry.transaction_id}")
            minimum = -account.overdraft_limit_minor if account.overdraft_eligible else 0
            if balance < minimum:
                raise ValueError(f"unauthorized negative balance on {entry.transaction_id}")

    transfers = session.scalars(select(TransferLink)).all()
    for transfer in transfers:
        source = session.get(Transaction, transfer.source_transaction_id)
        destination = session.get(Transaction, transfer.destination_transaction_id)
        if source is None or destination is None:
            raise ValueError(f"transfer {transfer.transfer_id} has a missing ledger leg")
        if (
            source.status != "posted"
            or destination.status != "posted"
            or source.account_id != transfer.source_account_id
            or destination.account_id != transfer.destination_account_id
            or source.currency != "USD"
            or destination.currency != "USD"
            or source.debit_minor != transfer.source_amount_minor
            or destination.credit_minor != transfer.destination_amount_minor
            or transfer.source_amount_minor != transfer.destination_amount_minor
            or transfer.status != "reconciled"
        ):
            raise ValueError(f"transfer reconciliation failed for {transfer.transfer_id}")

    alerts = session.scalars(select(Alert)).all()
    by_transaction_source: dict[tuple[str, str], list[Alert]] = defaultdict(list)
    for alert in alerts:
        if alert.triggering_transaction.status != "posted":
            raise ValueError(f"alert {alert.alert_id} does not reference a posted transaction")
        source = alert.evidence_json.get("source", "legacy")
        by_transaction_source[(alert.triggering_transaction_id, source)].append(alert)
    for (transaction_id, _), transaction_alerts in by_transaction_source.items():
        score = aggregate_score([alert.score_contribution_bps for alert in transaction_alerts])
        expected_priority = priority_for_score(score)
        if any(alert.priority != expected_priority for alert in transaction_alerts):
            raise ValueError(f"alert priority disagrees with aggregate score for {transaction_id}")
        if any(
            alert.evidence_json.get("aggregate_score_bps") not in (None, score)
            for alert in transaction_alerts
        ):
            raise ValueError(f"stored aggregate score disagrees with rule contributions for {transaction_id}")

    cases = session.scalars(select(Case)).all()
    for case in cases:
        linked_priorities = [
            link.alert.priority for link in case.alert_links if link.status == "linked"
        ]
        if linked_priorities:
            expected = min(linked_priorities, key=PRIORITY_ORDER.__getitem__)
            if case.priority != expected:
                raise ValueError(f"case priority mismatch for {case.case_id}")

    for link in session.scalars(select(CaseAlert).where(CaseAlert.status == "linked")):
        if link.linked_at < link.alert.detected_at:
            raise ValueError(f"case-alert link predates alert {link.case_alert_id}")
    for action in session.scalars(select(AnalystAction).where(AnalystAction.alert_id.is_not(None))):
        if action.alert_id and action.action_at < action.alert.detected_at:
            raise ValueError(f"analyst action predates alert {action.action_id}")

    return counts

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.models import Account, CustomerAccount, CustomerDevice, Transaction, TransferLink


def _effective_ownerships(session: Session, account_ids: set[str], at: datetime):
    if not account_ids:
        return []
    return session.scalars(
        select(CustomerAccount).where(
            CustomerAccount.account_id.in_(account_ids),
            CustomerAccount.status == "active",
            CustomerAccount.valid_from <= at,
            or_(CustomerAccount.valid_to.is_(None), CustomerAccount.valid_to > at),
        )
    ).all()


def analyze_account_links(
    session: Session,
    account_id: str,
    as_of: datetime | None = None,
    lookback_days: int = 30,
) -> dict[str, Any]:
    target = session.get(Account, account_id)
    if target is None:
        raise LookupError(f"Account {account_id} was not found.")
    at = as_of or datetime.now(timezone.utc)
    cutoff = at - timedelta(days=lookback_days)
    target_owners = _effective_ownerships(session, {account_id}, at)
    owner_ids = {row.customer_id for row in target_owners}
    reasons: dict[str, list[dict[str, Any]]] = {}

    def add(candidate: str, reason: dict[str, Any]) -> None:
        reasons.setdefault(candidate, []).append(reason)

    if owner_ids:
        related_ownerships = session.scalars(
            select(CustomerAccount).where(
                CustomerAccount.customer_id.in_(owner_ids),
                CustomerAccount.account_id != account_id,
                CustomerAccount.status == "active",
                CustomerAccount.valid_from <= at,
                or_(CustomerAccount.valid_to.is_(None), CustomerAccount.valid_to > at),
            )
        ).all()
        for ownership in related_ownerships:
            add(
                ownership.account_id,
                {"type": "shared_customer", "customer_id": ownership.customer_id},
            )

    target_device_links = session.scalars(
        select(CustomerDevice).where(
            CustomerDevice.customer_id.in_(owner_ids or {"__no_owner__"}),
            CustomerDevice.status == "active",
            CustomerDevice.first_seen_at <= at,
            or_(CustomerDevice.last_seen_at.is_(None), CustomerDevice.last_seen_at >= at),
        )
    ).all()
    device_ids = {row.device_id for row in target_device_links}
    target_transactions = session.scalars(
        select(Transaction).where(
            Transaction.account_id == account_id,
            Transaction.status == "posted",
            Transaction.device_id.is_not(None),
            Transaction.transaction_at >= cutoff,
            Transaction.transaction_at <= at,
        )
    ).all()
    device_ids.update(transaction.device_id for transaction in target_transactions)
    if device_ids:
        device_customer_ids = set(
            session.scalars(
                select(CustomerDevice.customer_id).where(
                    CustomerDevice.device_id.in_(device_ids),
                    CustomerDevice.status == "active",
                    CustomerDevice.first_seen_at <= at,
                    or_(CustomerDevice.last_seen_at.is_(None), CustomerDevice.last_seen_at >= at),
                )
            ).all()
        )
        device_ownerships = _effective_ownerships(
            session,
            {
                row.account_id
                for row in session.scalars(
                    select(CustomerAccount).where(
                        CustomerAccount.customer_id.in_(device_customer_ids),
                        CustomerAccount.status == "active",
                        CustomerAccount.valid_from <= at,
                        or_(CustomerAccount.valid_to.is_(None), CustomerAccount.valid_to > at),
                    )
                ).all()
            },
            at,
        )
        for ownership in device_ownerships:
            if ownership.account_id != account_id and ownership.customer_id not in owner_ids:
                add(
                    ownership.account_id,
                    {"type": "shared_device", "device_ids": sorted(device_ids)},
                )

    transfers = session.scalars(
        select(TransferLink).where(
            TransferLink.status == "reconciled",
            TransferLink.initiated_at >= cutoff,
            TransferLink.initiated_at <= at,
            or_(
                TransferLink.source_account_id == account_id,
                TransferLink.destination_account_id == account_id,
            ),
        )
    ).all()
    for transfer in transfers:
        other = (
            transfer.destination_account_id
            if transfer.source_account_id == account_id
            else transfer.source_account_id
        )
        add(
            other,
            {
                "type": "transfer",
                "transfer_id": transfer.transfer_id,
                "source_account_id": transfer.source_account_id,
                "destination_account_id": transfer.destination_account_id,
                "amount_minor": transfer.source_amount_minor,
            },
        )

    if device_ids and target_transactions:
        related_transactions = session.scalars(
            select(Transaction).where(
                Transaction.account_id != account_id,
                Transaction.status == "posted",
                Transaction.device_id.in_(device_ids),
                Transaction.transaction_at >= cutoff,
                Transaction.transaction_at <= at,
            )
        ).all()
        own_by_device: dict[str, list[Transaction]] = {}
        for own_tx in target_transactions:
            own_by_device.setdefault(own_tx.device_id, []).append(own_tx)
        for other_tx in related_transactions:
            for own_tx in own_by_device.get(other_tx.device_id, []):
                elapsed_seconds = abs(
                    (own_tx.transaction_at - other_tx.transaction_at).total_seconds()
                )
                add(
                    other_tx.account_id,
                    {
                        "type": "shared_device",
                        "device_id": own_tx.device_id,
                        "transaction_ids": sorted([own_tx.transaction_id, other_tx.transaction_id]),
                    },
                )
                if elapsed_seconds <= 3600:
                    add(
                        other_tx.account_id,
                        {
                            "type": "related_transaction_pattern",
                            "device_id": own_tx.device_id,
                            "transaction_ids": sorted([own_tx.transaction_id, other_tx.transaction_id]),
                            "within_minutes": round(elapsed_seconds / 60, 2),
                        },
                    )

    linked_accounts = []
    for candidate in sorted(reasons):
        linked_accounts.append(
            {
                "account_id": candidate,
                "reasons": sorted(
                    reasons[candidate],
                    key=lambda reason: (reason["type"], str(reason)),
                ),
            }
        )
    return {
        "account_id": account_id,
        "as_of": at,
        "linked_accounts": linked_accounts,
        "relationship_count": len(linked_accounts),
        "lookback_days": lookback_days,
    }

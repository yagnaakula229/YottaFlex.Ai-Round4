from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import Account, Transaction

SORT_COLUMNS = {
    "transaction_at": Transaction.transaction_at,
    "transaction_id": Transaction.transaction_id,
    "debit_minor": Transaction.debit_minor,
    "credit_minor": Transaction.credit_minor,
    "transaction_type": Transaction.transaction_type,
    "status": Transaction.status,
}


def list_transactions(
    session: Session,
    *,
    account_id: str | None = None,
    transaction_type: str | None = None,
    status: str | None = None,
    start_at: datetime | None = None,
    end_at: datetime | None = None,
    sort_by: str = "transaction_at",
    order: str = "desc",
    limit: int = 100,
    offset: int = 0,
) -> tuple[list[Transaction], int]:
    statement = select(Transaction)
    count_statement = select(func.count(Transaction.transaction_id))
    conditions = []
    if account_id:
        conditions.append(Transaction.account_id == account_id)
    if transaction_type:
        conditions.append(Transaction.transaction_type == transaction_type)
    if status:
        conditions.append(Transaction.status == status)
    if start_at:
        conditions.append(Transaction.transaction_at >= start_at)
    if end_at:
        conditions.append(Transaction.transaction_at <= end_at)
    if conditions:
        statement = statement.where(*conditions)
        count_statement = count_statement.where(*conditions)
    column = SORT_COLUMNS[sort_by]
    statement = statement.order_by(column.asc() if order == "asc" else column.desc())
    statement = statement.order_by(Transaction.transaction_id.asc()).limit(limit).offset(offset)
    return session.scalars(statement).all(), session.scalar(count_statement) or 0


def get_transaction(session: Session, transaction_id: str) -> Transaction | None:
    return session.get(Transaction, transaction_id)


def get_account_transactions(
    session: Session, account_id: str, *, limit: int = 100, offset: int = 0
) -> tuple[list[Transaction], int] | None:
    if session.get(Account, account_id) is None:
        return None
    statement = select(Transaction).where(Transaction.account_id == account_id)
    rows = session.scalars(
        statement.order_by(Transaction.transaction_at.desc(), Transaction.transaction_id.asc())
        .limit(limit)
        .offset(offset)
    ).all()
    total = session.scalar(
        select(func.count(Transaction.transaction_id)).where(Transaction.account_id == account_id)
    ) or 0
    return rows, total

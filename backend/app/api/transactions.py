from datetime import datetime
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.database.session import get_session
from app.schemas.common import Page
from app.schemas.transactions import TransactionRead
from app.services.link_analysis import analyze_account_links
from app.services.transaction_service import (
    get_account_transactions,
    get_transaction,
    list_transactions,
)

router = APIRouter(tags=["transactions", "accounts"])


@router.get("/transactions", response_model=Page[TransactionRead])
def transactions_list(
    account_id: str | None = None,
    transaction_type: Literal["purchase", "cash_withdrawal", "deposit", "transfer", "fee", "refund", "adjustment"] | None = None,
    status: Literal["pending", "posted", "declined", "voided"] | None = None,
    start_at: datetime | None = None,
    end_at: datetime | None = None,
    sort_by: Literal["transaction_at", "transaction_id", "debit_minor", "credit_minor", "transaction_type", "status"] = "transaction_at",
    order: Literal["asc", "desc"] = "desc",
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    session: Session = Depends(get_session),
):
    if any(
        value is not None and value.utcoffset() is None
        for value in (start_at, end_at)
    ):
        raise HTTPException(status_code=422, detail="timestamps must include a timezone")
    if start_at is not None and end_at is not None and end_at < start_at:
        raise HTTPException(status_code=422, detail="end_at must not precede start_at")
    rows, total = list_transactions(
        session,
        account_id=account_id,
        transaction_type=transaction_type,
        status=status,
        start_at=start_at,
        end_at=end_at,
        sort_by=sort_by,
        order=order,
        limit=limit,
        offset=offset,
    )
    return Page[TransactionRead](items=rows, total=total, limit=limit, offset=offset)


@router.get("/transactions/{transaction_id}", response_model=TransactionRead)
def transaction_detail(transaction_id: str, session: Session = Depends(get_session)):
    transaction = get_transaction(session, transaction_id)
    if transaction is None:
        raise HTTPException(status_code=404, detail="Transaction not found.")
    return transaction


@router.get("/accounts/{account_id}/transactions", response_model=Page[TransactionRead])
def account_transactions(
    account_id: str,
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    session: Session = Depends(get_session),
):
    result = get_account_transactions(session, account_id, limit=limit, offset=offset)
    if result is None:
        raise HTTPException(status_code=404, detail="Account not found.")
    rows, total = result
    return Page[TransactionRead](items=rows, total=total, limit=limit, offset=offset)


@router.get("/accounts/{account_id}/links")
def account_links(
    account_id: str,
    lookback_days: int = Query(default=30, ge=1, le=365),
    session: Session = Depends(get_session),
):
    try:
        return analyze_account_links(session, account_id, lookback_days=lookback_days)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

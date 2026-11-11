from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.database.session import get_session
from app.models import Transaction
from app.schemas.alerts import RiskEvaluationRequest
from app.services.risk_service import evaluate_transactions

router = APIRouter(prefix="/risk", tags=["risk"])


@router.post("/evaluate")
def risk_evaluate(
    request: RiskEvaluationRequest,
    session: Session = Depends(get_session),
):
    if request.transaction_id:
        transaction = session.scalar(
            select(Transaction).where(Transaction.transaction_id == request.transaction_id)
        )
        if transaction is None:
            raise HTTPException(status_code=404, detail="Transaction not found.")
        if transaction.status != "posted":
            raise HTTPException(status_code=422, detail="Only posted transactions can be evaluated.")
    return evaluate_transactions(
        session,
        transaction_id=request.transaction_id,
        limit=request.limit,
        after_transaction_at=request.after_transaction_at,
        after_transaction_id=request.after_transaction_id,
    )

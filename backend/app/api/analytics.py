from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database.session import get_session
from app.schemas.analytics import DashboardSummary, EvaluationMetrics
from app.services.analytics_service import dashboard_summary
from app.services.evaluation_service import evaluate_ground_truth

router = APIRouter(tags=["analytics"])


@router.get("/dashboard/summary", response_model=DashboardSummary)
def dashboard(session: Session = Depends(get_session)):
    return dashboard_summary(session)


@router.get("/analytics/evaluation", response_model=EvaluationMetrics)
def evaluation(session: Session = Depends(get_session)):
    try:
        return evaluate_ground_truth(session)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc

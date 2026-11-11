from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.database.session import get_session
from app.schemas.cases import (
    AnalystActionCreate,
    AnalystActionRead,
    CaseDetail,
    CaseGroupResult,
    CaseListItem,
)
from app.schemas.common import Page
from app.services.case_service import (
    action_to_read,
    get_case_detail,
    group_related_alerts,
    list_cases,
    record_analyst_action,
)

router = APIRouter(prefix="/cases", tags=["cases", "analyst-actions"])


@router.get("", response_model=Page[CaseListItem])
def cases_list(
    status: Literal["open", "in_review", "escalated", "resolved", "closed"] | None = None,
    priority: Literal["P1", "P2", "P3", "P4"] | None = None,
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    session: Session = Depends(get_session),
):
    rows, total = list_cases(
        session, status=status, priority=priority, limit=limit, offset=offset
    )
    return Page[CaseListItem](items=rows, total=total, limit=limit, offset=offset)


@router.post("/group", response_model=CaseGroupResult)
def cases_group(
    limit: int = Query(default=1000, ge=2, le=5000),
    session: Session = Depends(get_session),
):
    return group_related_alerts(session, limit=limit)


@router.get("/{case_id}", response_model=CaseDetail)
def case_detail(case_id: str, session: Session = Depends(get_session)):
    result = get_case_detail(session, case_id)
    if result is None:
        raise HTTPException(status_code=404, detail="Case not found.")
    return result


@router.post("/{case_id}/actions", response_model=AnalystActionRead, status_code=201)
def case_action(
    case_id: str,
    payload: AnalystActionCreate,
    session: Session = Depends(get_session),
):
    try:
        action = record_analyst_action(session, case_id, payload.model_dump())
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return action_to_read(action)

from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session, joinedload

from app.database.session import get_session
from app.models import Alert
from app.schemas.alerts import AlertRead
from app.schemas.common import Page
from app.services.risk_service import alert_aggregate_scores, alert_to_read

router = APIRouter(prefix="/alerts", tags=["alerts"])


@router.get("", response_model=Page[AlertRead])
def alerts_list(
    priority: Literal["P1", "P2", "P3", "P4"] | None = None,
    status: Literal["new", "acknowledged", "in_review", "escalated", "resolved", "closed"] | None = None,
    rule_id: str | None = None,
    transaction_id: str | None = None,
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    session: Session = Depends(get_session),
):
    statement = select(Alert).options(joinedload(Alert.rule))
    count_statement = select(func.count(Alert.alert_id))
    conditions = []
    if priority:
        conditions.append(Alert.priority == priority)
    if status:
        conditions.append(Alert.status == status)
    if rule_id:
        conditions.append(Alert.rule_id == rule_id)
    if transaction_id:
        conditions.append(Alert.triggering_transaction_id == transaction_id)
    if conditions:
        statement = statement.where(*conditions)
        count_statement = count_statement.where(*conditions)
    alerts = session.scalars(
        statement.order_by(Alert.detected_at.desc(), Alert.alert_id).limit(limit).offset(offset)
    ).all()
    total = session.scalar(count_statement) or 0
    aggregate_scores = alert_aggregate_scores(
        session, {alert.triggering_transaction_id for alert in alerts}
    )
    return Page[AlertRead](
        items=[
            alert_to_read(
                session,
                alert,
                aggregate_scores.get(
                    (
                        alert.triggering_transaction_id,
                        alert.evidence_json.get("source", "legacy"),
                    ),
                    0,
                ),
            )
            for alert in alerts
        ],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get("/{alert_id}", response_model=AlertRead)
def alert_detail(alert_id: str, session: Session = Depends(get_session)):
    alert = session.scalar(
        select(Alert).options(joinedload(Alert.rule)).where(Alert.alert_id == alert_id)
    )
    if alert is None:
        raise HTTPException(status_code=404, detail="Alert not found.")
    return alert_to_read(session, alert)

from datetime import datetime
from typing import Any

from datetime import datetime

from pydantic import BaseModel, Field, model_validator


class AlertRead(BaseModel):
    alert_id: str
    rule_id: str
    rule_key: str
    rule_version: int
    triggering_transaction_id: str
    status: str
    priority: str
    score_contribution_bps: int
    aggregate_score_bps: int
    explanation: str
    evidence: dict[str, Any]
    evaluated_at: datetime
    detected_at: datetime


class RiskEvaluationRequest(BaseModel):
    transaction_id: str | None = None
    limit: int = Field(default=500, ge=1, le=10_000)
    after_transaction_at: datetime | None = None
    after_transaction_id: str | None = None

    @model_validator(mode="after")
    def validate_cursor(self):
        if (self.after_transaction_at is None) != (self.after_transaction_id is None):
            raise ValueError("Both cursor fields must be provided together.")
        if self.transaction_id and self.after_transaction_at is not None:
            raise ValueError("A transaction_id cannot be combined with a batch cursor.")
        if self.after_transaction_at is not None and self.after_transaction_at.tzinfo is None:
            raise ValueError("Cursor timestamp must include a timezone.")
        return self

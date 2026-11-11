from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator, model_validator


class CaseListItem(BaseModel):
    case_id: str
    title: str
    status: str
    priority: str
    alert_count: int
    created_at: datetime
    updated_at: datetime


class CaseDetail(CaseListItem):
    alerts: list[dict[str, Any]]
    actions: list[dict[str, Any]]
    audit_events: list[dict[str, Any]]


class AnalystActionCreate(BaseModel):
    action_type: Literal[
        "review_started",
        "note_added",
        "disposition_recorded",
        "status_changed",
        "escalated",
        "case_closed",
        "case_reopened",
    ]
    disposition: str | None = None
    alert_id: str | None = None
    target_status: str | None = None
    note: str | None = Field(default=None, max_length=500)
    idempotency_key: str | None = Field(default=None, max_length=128)

    @field_validator("disposition", mode="before")
    @classmethod
    def normalize_disposition(cls, value):
        if value is None:
            return None
        aliases = {
            "CONFIRMED_SUSPICIOUS": "suspicious",
            "SUSPICIOUS": "suspicious",
            "FALSE_POSITIVE": "false_positive",
            "LEGITIMATE": "false_positive",
            "INCONCLUSIVE": "inconclusive",
            "NEEDS_MORE_INFORMATION": "inconclusive",
            "REFERRED": "referred",
        }
        return aliases.get(str(value).upper(), value)

    @model_validator(mode="after")
    def validate_action_fields(self):
        if self.action_type == "disposition_recorded" and self.disposition is None:
            raise ValueError("disposition is required for disposition_recorded")
        if self.disposition is not None and self.disposition not in {
            "suspicious",
            "false_positive",
            "inconclusive",
            "referred",
        }:
            raise ValueError("unsupported disposition")
        if self.disposition is not None and self.action_type != "disposition_recorded":
            raise ValueError("disposition is only valid for disposition_recorded")
        if self.action_type == "status_changed" and self.target_status is None:
            raise ValueError("target_status is required for status_changed")
        if self.target_status is not None and self.action_type != "status_changed":
            raise ValueError("target_status is only valid for status_changed")
        return self


class AnalystActionRead(BaseModel):
    action_id: str
    case_id: str
    alert_id: str | None
    action_type: str
    disposition: str | None
    actor_id: str
    action_at: datetime
    note: str | None
    details_json: dict[str, Any]


class CaseGroupResult(BaseModel):
    cases_created: int
    case_ids: list[str]
    attached_case_ids: list[str]
    alert_count: int

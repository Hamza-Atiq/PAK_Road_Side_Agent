"""Pydantic schemas for the Incidents API."""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.models.enums import IncidentStatus


# ---------- Responses ----------


class IncidentResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    customer_id: uuid.UUID
    provider_id: uuid.UUID | None = None
    status: str
    lat: float
    lng: float
    address: str | None = None
    description: str | None = None
    image_url: str | None = None
    voice_url: str | None = None
    ai_diagnosis: dict[str, Any] | None = None
    eta_minutes: int | None = None
    guardrail_flagged: bool = False
    created_at: datetime
    updated_at: datetime
    completed_at: datetime | None = None


class IncidentBrief(BaseModel):
    """Lightweight listing entry — used by /my, /assigned, admin /."""
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    status: str
    lat: float
    lng: float
    provider_id: uuid.UUID | None = None
    eta_minutes: int | None = None
    created_at: datetime
    updated_at: datetime


class IncidentListResponse(BaseModel):
    total: int
    limit: int
    offset: int
    items: list[IncidentBrief]


class IncidentCreateResponse(BaseModel):
    id: uuid.UUID
    status: str
    queued: bool
    message: str


# ---------- Requests ----------


# The state machine in db_write_tool already validates which transitions are
# allowed. We just constrain the values that can be requested via the API.
_PROVIDER_ALLOWED = {
    IncidentStatus.EN_ROUTE.value,
    IncidentStatus.ARRIVED.value,
    IncidentStatus.COMPLETED.value,
}
_ADMIN_ALLOWED = {s.value for s in IncidentStatus}


class StatusUpdateRequest(BaseModel):
    new_status: str
    reason: str | None = Field(default=None, max_length=500)

    @field_validator("new_status")
    @classmethod
    def _is_known(cls, v: str) -> str:
        if v not in _ADMIN_ALLOWED:
            raise ValueError(
                f"unknown status '{v}'. Allowed: {sorted(_ADMIN_ALLOWED)}"
            )
        return v


class CloseIncidentRequest(BaseModel):
    reason: str | None = Field(default=None, max_length=500)

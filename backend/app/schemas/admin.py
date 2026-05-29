"""Pydantic schemas for the Admin API."""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

import phonenumbers
from pydantic import BaseModel, ConfigDict, Field, field_validator


def _normalize_phone(raw: str) -> str:
    if not raw:
        raise ValueError("phone is required")
    try:
        parsed = phonenumbers.parse(raw, None)
    except phonenumbers.NumberParseException as exc:
        raise ValueError(f"invalid phone format: {exc}") from exc
    if not phonenumbers.is_possible_number(parsed):
        raise ValueError("phone is not a possible number for any region")
    return phonenumbers.format_number(parsed, phonenumbers.PhoneNumberFormat.E164)


# ---------- Dashboard ----------


class IncidentCountsByStatus(BaseModel):
    REPORTED: int = 0
    ANALYZING: int = 0
    ASSIGNED: int = 0
    NO_PROVIDER: int = 0
    ESCALATED: int = 0
    EN_ROUTE: int = 0
    ARRIVED: int = 0
    COMPLETED: int = 0
    CLOSED: int = 0


class ProviderCounts(BaseModel):
    total_approved: int = 0
    available_now: int = 0
    online_pingers: int = 0  # last_ping within 90 s
    on_active_job: int = 0


class MessagingStats(BaseModel):
    total_24h: int = 0
    delivered_24h: int = 0
    failed_24h: int = 0
    delivery_rate: float = Field(default=1.0, ge=0.0, le=1.0)


class DashboardResponse(BaseModel):
    incidents_by_status: IncidentCountsByStatus
    incident_counts_24h: int
    providers: ProviderCounts
    messaging: MessagingStats
    open_incidents_count: int  # not in COMPLETED/CLOSED/ESCALATED
    avg_eta_minutes_24h: float | None = None
    generated_at: datetime


# ---------- Notify ----------


class NotifyRequest(BaseModel):
    to_phone: str
    body: str = Field(..., min_length=1, max_length=1000)
    channel: str = Field(default="sms", pattern="^(sms|whatsapp)$")
    incident_id: uuid.UUID | None = None

    @field_validator("to_phone")
    @classmethod
    def _phone(cls, v: str) -> str:
        return _normalize_phone(v)


class NotifyResponse(BaseModel):
    message_id: uuid.UUID
    twilio_sid: str | None
    delivery_status: str


# ---------- Reassign ----------


class ReassignRequest(BaseModel):
    new_provider_id: uuid.UUID | None = Field(
        default=None,
        description="If null, AdminAgent runs DispatchAgent to pick automatically.",
    )
    reason: str | None = Field(default=None, max_length=500)


class ReassignResponse(BaseModel):
    incident_id: uuid.UUID
    new_provider_id: uuid.UUID | None
    new_provider_name: str | None
    status: str
    notes: str


# ---------- Suspend ----------


class SuspendRequest(BaseModel):
    reason: str | None = Field(default=None, max_length=500)


# ---------- NL Query ----------


class AdminQueryRequest(BaseModel):
    query: str = Field(..., min_length=1, max_length=1000)


class AdminQueryResponse(BaseModel):
    intent: str
    summary: str
    data: dict[str, Any] | None = None
    actioned: bool = False


# ---------- Misc helpers ----------


class IncidentBrief(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    status: str
    lat: float
    lng: float
    created_at: datetime
    provider_id: uuid.UUID | None = None


class ProviderBrief(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    service_type: str
    is_available: bool
    is_approved: bool
    total_jobs: int
    last_ping: datetime | None = None

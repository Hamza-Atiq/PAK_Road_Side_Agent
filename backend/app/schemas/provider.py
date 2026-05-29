"""Pydantic schemas for the Providers API."""
from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class ProviderProfile(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    service_type: str
    vehicle_info: str | None = None
    is_available: bool
    is_approved: bool
    total_jobs: int
    last_ping: datetime | None = None


class ProviderListItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    phone: str
    service_type: str
    is_available: bool
    is_approved: bool
    total_jobs: int
    last_ping: datetime | None = None


class ProviderListResponse(BaseModel):
    total: int
    items: list[ProviderListItem]


class ProviderUpdateRequest(BaseModel):
    service_type: str | None = Field(default=None, max_length=50)
    vehicle_info: str | None = Field(default=None, max_length=500)


class AvailabilityRequest(BaseModel):
    is_available: bool


class LocationPingRequest(BaseModel):
    lat: float = Field(..., ge=-90.0, le=90.0)
    lng: float = Field(..., ge=-180.0, le=180.0)


class LocationPingResponse(BaseModel):
    provider_id: uuid.UUID
    last_ping: datetime
    is_available: bool

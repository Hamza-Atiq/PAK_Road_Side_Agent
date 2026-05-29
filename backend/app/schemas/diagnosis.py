"""Diagnosis schema produced by vision_tool and consumed by TriageAgent.

Strict validation: agents never produce free-form `service_needed` strings.
Only values from the `ServiceType` enum are allowed; the dispatcher relies on
this to match incidents to providers correctly.
"""
from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.models.enums import IncidentSeverity, ServiceType


class DiagnosisResult(BaseModel):
    """Structured output of a vehicle-issue diagnosis (image, voice, or text)."""

    model_config = ConfigDict(use_enum_values=True)

    issue_type: str = Field(
        ..., max_length=100,
        description="Short label, e.g. 'flat tire', 'dead battery', 'engine overheating'.",
    )
    severity: IncidentSeverity = Field(
        default=IncidentSeverity.unknown,
        description="low | medium | high | critical | unknown",
    )
    service_needed: ServiceType = Field(
        ..., description="Must be one of ServiceType enum values.",
    )
    confidence: float = Field(
        ..., ge=0.0, le=1.0,
        description="Model self-rated confidence in this diagnosis (0.0-1.0).",
    )
    details: str | None = Field(
        default=None, max_length=1000,
        description="Free-text supporting notes for the dispatcher/provider.",
    )

    @field_validator("issue_type")
    @classmethod
    def _strip_issue(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("issue_type must not be empty")
        return v

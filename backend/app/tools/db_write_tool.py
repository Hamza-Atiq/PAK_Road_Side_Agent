"""Validated database write operations exposed to agents.

Agents never construct raw ORM updates. They call these functions, which:
- Enforce state-machine transitions (incident status changes)
- Enforce business invariants (a provider can only hold one active job)
- Always go through SQLAlchemy ORM (no string interpolation)
- Are testable independently

DbWriteError is raised for any invalid request — the caller (agent) decides
how to react (retry, escalate, surface to user).
"""
from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.middleware.logging import get_logger
from app.models.enums import IncidentStatus, TaskLogStatus
from app.models.incident import Incident
from app.models.provider import Provider
from app.models.task_log import TaskLog
from app.models.user import User

log = get_logger("tools.db_write")


# ----------------------------------------------------------------------
# Error
# ----------------------------------------------------------------------


class DbWriteError(Exception):
    pass


# ----------------------------------------------------------------------
# State machine — allowed status transitions
# ----------------------------------------------------------------------


_ALLOWED_TRANSITIONS: dict[str, set[str]] = {
    IncidentStatus.REPORTED.value:    {IncidentStatus.ANALYZING.value, IncidentStatus.CLOSED.value},
    IncidentStatus.ANALYZING.value:   {IncidentStatus.ASSIGNED.value,
                                       IncidentStatus.NO_PROVIDER.value,
                                       IncidentStatus.ESCALATED.value,
                                       IncidentStatus.CLOSED.value},
    IncidentStatus.ASSIGNED.value:    {IncidentStatus.EN_ROUTE.value,
                                       IncidentStatus.NO_PROVIDER.value,
                                       IncidentStatus.ESCALATED.value,
                                       IncidentStatus.CLOSED.value},
    IncidentStatus.NO_PROVIDER.value: {IncidentStatus.ASSIGNED.value,
                                       IncidentStatus.ESCALATED.value,
                                       IncidentStatus.CLOSED.value},
    IncidentStatus.ESCALATED.value:   {IncidentStatus.ASSIGNED.value,
                                       IncidentStatus.CLOSED.value},
    IncidentStatus.EN_ROUTE.value:    {IncidentStatus.ARRIVED.value,
                                       IncidentStatus.NO_PROVIDER.value,
                                       IncidentStatus.ESCALATED.value,
                                       IncidentStatus.CLOSED.value},
    IncidentStatus.ARRIVED.value:     {IncidentStatus.COMPLETED.value,
                                       IncidentStatus.ESCALATED.value,
                                       IncidentStatus.CLOSED.value},
    IncidentStatus.COMPLETED.value:   {IncidentStatus.CLOSED.value},
    IncidentStatus.CLOSED.value:      set(),
}


def _validate_transition(current: str, target: str) -> None:
    if current == target:
        return  # idempotent
    allowed = _ALLOWED_TRANSITIONS.get(current, set())
    if target not in allowed:
        raise DbWriteError(
            f"invalid status transition: {current} → {target}. "
            f"Allowed from {current}: {sorted(allowed) or 'none (terminal)'}"
        )


# ----------------------------------------------------------------------
# Writes
# ----------------------------------------------------------------------


async def update_incident_status(
    db: AsyncSession,
    *,
    incident_id: uuid.UUID,
    new_status: IncidentStatus,
    reason: str | None = None,
    ai_diagnosis: dict[str, Any] | None = None,
    eta_minutes: int | None = None,
) -> Incident:
    """Transition an incident to `new_status` with optional metadata updates.

    Validates the transition against the state machine.
    """
    incident = await db.get(Incident, incident_id)
    if incident is None:
        raise DbWriteError(f"incident {incident_id} not found")

    _validate_transition(incident.status, new_status.value)

    incident.status = new_status.value
    incident.updated_at = datetime.now(UTC)
    if ai_diagnosis is not None:
        incident.ai_diagnosis = ai_diagnosis
    if eta_minutes is not None:
        incident.eta_minutes = eta_minutes
    if new_status == IncidentStatus.COMPLETED:
        incident.completed_at = datetime.now(UTC)

    await db.flush()
    log.info(
        "incident_status_updated",
        incident_id=str(incident_id),
        new_status=new_status.value,
        reason=reason,
    )
    return incident


async def assign_provider_to_incident(
    db: AsyncSession,
    *,
    incident_id: uuid.UUID,
    provider_id: uuid.UUID,
    eta_minutes: int,
    ai_diagnosis: dict[str, Any] | None = None,
) -> Incident:
    """Assign `provider_id` to `incident_id`, set status=ASSIGNED, mark provider
    unavailable for new jobs. Enforces:
    - provider exists, is approved, is available
    - incident exists and is in a state that can transition to ASSIGNED
    """
    incident = await db.get(Incident, incident_id)
    if incident is None:
        raise DbWriteError(f"incident {incident_id} not found")

    provider_user = await db.get(User, provider_id)
    if provider_user is None or provider_user.role != "provider":
        raise DbWriteError(f"user {provider_id} is not a provider")
    if not provider_user.is_active:
        raise DbWriteError(f"provider {provider_id} account is inactive")

    provider = await db.get(Provider, provider_id)
    if provider is None:
        raise DbWriteError(f"provider profile {provider_id} not found")
    if not provider.is_approved:
        raise DbWriteError(f"provider {provider_id} is not approved")
    if not provider.is_available:
        raise DbWriteError(f"provider {provider_id} is not available")

    # Verify the provider isn't already on an active job
    from sqlalchemy import or_
    active = await db.scalar(
        select(Incident.id)
        .where(Incident.provider_id == provider_id)
        .where(
            or_(
                Incident.status == IncidentStatus.ASSIGNED.value,
                Incident.status == IncidentStatus.EN_ROUTE.value,
                Incident.status == IncidentStatus.ARRIVED.value,
            )
        )
        .limit(1)
    )
    if active is not None:
        raise DbWriteError(
            f"provider {provider_id} is already on active job {active}"
        )

    _validate_transition(incident.status, IncidentStatus.ASSIGNED.value)

    incident.provider_id = provider_id
    incident.status = IncidentStatus.ASSIGNED.value
    incident.eta_minutes = eta_minutes
    incident.updated_at = datetime.now(UTC)
    if ai_diagnosis is not None:
        incident.ai_diagnosis = ai_diagnosis

    # Take the provider off the available pool until job completes
    provider.is_available = False

    await db.flush()
    log.info(
        "provider_assigned",
        incident_id=str(incident_id),
        provider_id=str(provider_id),
        eta_minutes=eta_minutes,
    )
    return incident


async def release_provider_availability(
    db: AsyncSession, *, provider_id: uuid.UUID
) -> None:
    """Mark a provider available again after a job completes or is reassigned."""
    provider = await db.get(Provider, provider_id)
    if provider is None:
        raise DbWriteError(f"provider {provider_id} not found")
    provider.is_available = True
    await db.flush()


async def log_agent_step(
    db: AsyncSession,
    *,
    incident_id: uuid.UUID | None,
    agent_name: str,
    step: str,
    status: TaskLogStatus,
    reasoning: str | None = None,
    payload: dict[str, Any] | None = None,
    error: str | None = None,
    duration_ms: int | None = None,
) -> TaskLog:
    """Append a row to task_logs. Exposed as a tool so EscalationAgent and
    other helpers can log without holding a BaseAgent instance.
    """
    row = TaskLog(
        incident_id=incident_id,
        agent_name=agent_name,
        step=step,
        status=status.value,
        reasoning=reasoning,
        payload=payload,
        error=error,
        duration_ms=duration_ms,
    )
    db.add(row)
    await db.flush()
    return row

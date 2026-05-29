"""TrackingAgent — periodic scanner for stalled jobs and offline providers.

Runs every 60 seconds via Celery beat (see celery_worker.py). For each
anomaly it finds, it spawns EscalationAgent with the appropriate reason
code; EscalationAgent decides the recovery action.

The thresholds are read from `settings` so ops can tune them without a deploy:
- PROVIDER_OFFLINE_THRESHOLD_SECONDS  (default 90s)
- ASSIGNED_TIMEOUT_MINUTES            (default 60min)
- EN_ROUTE_TIMEOUT_MINUTES            (default 180min)
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta

from sqlalchemy import and_, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.base import AgentContext, BaseAgent
from app.agents.escalation import EscalationAgent, EscalationReason
from app.config import settings
from app.middleware.logging import get_logger
from app.models.enums import IncidentStatus
from app.models.incident import Incident
from app.models.provider import Provider

log = get_logger("agents.tracking")


# ----------------------------------------------------------------------
# Result
# ----------------------------------------------------------------------


@dataclass
class TrackingScanResult:
    """Summary of one scan pass — useful for metrics and admin dashboards."""

    offline_provider_count: int = 0
    stalled_assignment_count: int = 0
    stalled_en_route_count: int = 0
    stale_no_provider_count: int = 0
    escalations_triggered: int = 0
    incident_ids_escalated: list[uuid.UUID] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "offline_provider_count": self.offline_provider_count,
            "stalled_assignment_count": self.stalled_assignment_count,
            "stalled_en_route_count": self.stalled_en_route_count,
            "stale_no_provider_count": self.stale_no_provider_count,
            "escalations_triggered": self.escalations_triggered,
            "incident_ids_escalated": [str(i) for i in self.incident_ids_escalated],
        }


# ----------------------------------------------------------------------
# Detection queries
# ----------------------------------------------------------------------


_ACTIVE_JOB_STATUSES = (
    IncidentStatus.ASSIGNED.value,
    IncidentStatus.EN_ROUTE.value,
    IncidentStatus.ARRIVED.value,
)


async def _find_offline_provider_incidents(
    db: AsyncSession, *, ping_threshold_seconds: int
) -> list[Incident]:
    """Active jobs whose assigned provider hasn't pinged within the threshold.

    A `last_ping` of NULL is also considered offline (provider never started
    sending GPS).
    """
    cutoff = datetime.now(UTC) - timedelta(seconds=ping_threshold_seconds)
    stmt = (
        select(Incident)
        .join(Provider, Provider.id == Incident.provider_id)
        .where(Incident.status.in_(_ACTIVE_JOB_STATUSES))
        .where(
            or_(
                Provider.last_ping.is_(None),
                Provider.last_ping < cutoff,
            )
        )
    )
    result = await db.execute(stmt)
    return list(result.scalars())


async def _find_stalled_assignments(
    db: AsyncSession, *, assigned_timeout_minutes: int
) -> list[Incident]:
    """Incidents in ASSIGNED state longer than the configured timeout.

    `updated_at` is set on every status change, so an incident that was
    ASSIGNED N minutes ago and hasn't moved means the provider never
    transitioned to EN_ROUTE.
    """
    cutoff = datetime.now(UTC) - timedelta(minutes=assigned_timeout_minutes)
    stmt = (
        select(Incident)
        .where(Incident.status == IncidentStatus.ASSIGNED.value)
        .where(Incident.updated_at < cutoff)
    )
    result = await db.execute(stmt)
    return list(result.scalars())


async def _find_stalled_en_route(
    db: AsyncSession, *, en_route_timeout_minutes: int
) -> list[Incident]:
    """Incidents stuck EN_ROUTE longer than the configured timeout."""
    cutoff = datetime.now(UTC) - timedelta(minutes=en_route_timeout_minutes)
    stmt = (
        select(Incident)
        .where(Incident.status == IncidentStatus.EN_ROUTE.value)
        .where(Incident.updated_at < cutoff)
    )
    result = await db.execute(stmt)
    return list(result.scalars())


# How long an incident may sit in NO_PROVIDER before we re-alert the admin.
# Hard-coded rather than env-configurable: this is a UX guarantee, not a knob.
STALE_NO_PROVIDER_MINUTES = 2


async def _find_stale_no_provider(db: AsyncSession) -> list[Incident]:
    """Incidents stuck in NO_PROVIDER longer than STALE_NO_PROVIDER_MINUTES.

    Spec §10.3: admin gets re-alerted every scan tick after this threshold
    until they resolve the incident.
    """
    cutoff = datetime.now(UTC) - timedelta(minutes=STALE_NO_PROVIDER_MINUTES)
    stmt = (
        select(Incident)
        .where(Incident.status == IncidentStatus.NO_PROVIDER.value)
        .where(Incident.updated_at < cutoff)
    )
    result = await db.execute(stmt)
    return list(result.scalars())


# ----------------------------------------------------------------------
# TrackingAgent
# ----------------------------------------------------------------------


class TrackingAgent(BaseAgent[TrackingScanResult]):
    name = "TrackingAgent"
    persona = (
        "Vigilant monitor. Watches active jobs in the background. Notices "
        "what humans wouldn't catch in time."
    )
    goal = "Detect every stalled job or offline provider before customers complain."
    # No Claude calls — deterministic SQL scan that delegates recovery.
    tools = ("db_read_tool", "spawn_agent")

    def __init__(
        self,
        anthropic_client=None,
        *,
        escalation: EscalationAgent | None = None,
    ) -> None:
        super().__init__(anthropic_client=anthropic_client)
        self.escalation = escalation or EscalationAgent(anthropic_client=anthropic_client)

    async def _execute(self, context: AgentContext) -> TrackingScanResult:
        result = TrackingScanResult()

        # ----- 1. Offline providers on active jobs -----
        offline_incidents = await _find_offline_provider_incidents(
            context.db,
            ping_threshold_seconds=settings.PROVIDER_OFFLINE_THRESHOLD_SECONDS,
        )
        result.offline_provider_count = len(offline_incidents)
        for incident in offline_incidents:
            await self._escalate(
                context, incident,
                reason=EscalationReason.PROVIDER_OFFLINE,
                result=result,
            )

        # ----- 2. Stalled ASSIGNED (provider accepted but never moved) -----
        # Skip any incident already handled above (it'd be redundant).
        already_handled = {i.id for i in offline_incidents}
        stalled_assignments = [
            i for i in await _find_stalled_assignments(
                context.db, assigned_timeout_minutes=settings.ASSIGNED_TIMEOUT_MINUTES,
            )
            if i.id not in already_handled
        ]
        result.stalled_assignment_count = len(stalled_assignments)
        for incident in stalled_assignments:
            await self._escalate(
                context, incident,
                reason=EscalationReason.STALLED_ASSIGNMENT,
                result=result,
            )
            already_handled.add(incident.id)

        # ----- 3. Stalled EN_ROUTE (admin alert only — don't preempt driver) -----
        stalled_en_route = [
            i for i in await _find_stalled_en_route(
                context.db, en_route_timeout_minutes=settings.EN_ROUTE_TIMEOUT_MINUTES,
            )
            if i.id not in already_handled
        ]
        result.stalled_en_route_count = len(stalled_en_route)
        for incident in stalled_en_route:
            await self._escalate(
                context, incident,
                reason=EscalationReason.STALLED_EN_ROUTE,
                result=result,
            )
            already_handled.add(incident.id)

        # ----- 4. Stale NO_PROVIDER (re-alert admin until acted upon) -----
        stale_no_provider = [
            i for i in await _find_stale_no_provider(context.db)
            if i.id not in already_handled
        ]
        result.stale_no_provider_count = len(stale_no_provider)
        for incident in stale_no_provider:
            await self._escalate(
                context, incident,
                reason=EscalationReason.NO_PROVIDER,
                result=result,
            )

        log.info(
            "tracking_scan_complete",
            offline=result.offline_provider_count,
            stalled_assigned=result.stalled_assignment_count,
            stalled_en_route=result.stalled_en_route_count,
            stale_no_provider=result.stale_no_provider_count,
            escalations=result.escalations_triggered,
        )
        return result

    async def _escalate(
        self,
        context: AgentContext,
        incident: Incident,
        *,
        reason: EscalationReason,
        result: TrackingScanResult,
    ) -> None:
        esc_ctx = AgentContext(
            db=context.db,
            incident_id=incident.id,
            payload={"reason": reason.value},
        )
        try:
            await self.escalation.run(esc_ctx)
        except Exception as exc:  # noqa: BLE001
            log.exception("escalation_failed_during_tracking",
                          incident_id=str(incident.id), reason=reason.value)
            return
        result.escalations_triggered += 1
        result.incident_ids_escalated.append(incident.id)

"""EscalationAgent — autonomous recovery for failure scenarios.

The escalation reason in `context.payload["reason"]` routes the agent to one
of five handlers:

    NO_PROVIDER         → broadcast NO_PROVIDER alert + SMS every active admin.
    PROVIDER_OFFLINE    → release the absent provider, mark NO_PROVIDER, run DispatchAgent
                          again for replacement. If replacement found → customer kept informed.
                          If not → admin alert.
    STALLED_ASSIGNMENT  → same as PROVIDER_OFFLINE (provider accepted but never
                          set EN_ROUTE within the timeout).
    STALLED_EN_ROUTE    → admin alert only. We don't preempt an active driver; the
                          admin decides whether to push or reassign.
    REPEATED_FAILURE    → mark incident ESCALATED (terminal until human action),
                          summarize and alert admin.

The agent's tool allow-list reflects what each handler actually does — no
Claude reasoning needed at this layer; the recovery logic is deterministic
and auditable. The "agentic" character of recovery comes from DispatchAgent
re-running, which itself reasons across candidate providers.
"""
from __future__ import annotations

import enum
import uuid
from dataclasses import dataclass

from app.agents.base import AgentContext, AgentExecutionError, BaseAgent
from app.agents.communication import CommunicationAgent
from app.agents.dispatch import DispatchAgent, DispatchResult
from app.metrics import incidents_escalated_total, provider_offline_detections_total
from app.middleware.logging import get_logger
from app.models.enums import IncidentStatus, TaskLogStatus
from app.tools.db_read_tool import get_active_admins, get_incident, get_user
from app.tools.db_write_tool import (
    DbWriteError,
    release_provider_availability,
    update_incident_status,
)
from app.tools.notification_tool import broadcast_incident_event

log = get_logger("agents.escalation")


# ----------------------------------------------------------------------
# Reason enum
# ----------------------------------------------------------------------


class EscalationReason(str, enum.Enum):
    NO_PROVIDER = "NO_PROVIDER"
    PROVIDER_OFFLINE = "PROVIDER_OFFLINE"
    STALLED_ASSIGNMENT = "STALLED_ASSIGNMENT"
    STALLED_EN_ROUTE = "STALLED_EN_ROUTE"
    REPEATED_FAILURE = "REPEATED_FAILURE"


# ----------------------------------------------------------------------
# Result
# ----------------------------------------------------------------------


@dataclass
class EscalationOutcome:
    reason: str
    incident_id: uuid.UUID
    new_status: str
    redispatched: bool
    new_provider_id: uuid.UUID | None
    admin_alerted: bool
    notes: str

    def to_dict(self) -> dict:
        return {
            "reason": self.reason,
            "incident_id": str(self.incident_id),
            "new_status": self.new_status,
            "redispatched": self.redispatched,
            "new_provider_id": str(self.new_provider_id) if self.new_provider_id else None,
            "admin_alerted": self.admin_alerted,
            "notes": self.notes[:500],
        }


# ----------------------------------------------------------------------
# EscalationAgent
# ----------------------------------------------------------------------


class EscalationAgent(BaseAgent[EscalationOutcome]):
    name = "EscalationAgent"
    persona = (
        "Crisis handler. Stays calm, never loops, always takes a concrete action: "
        "reassign, alert, or escalate to human."
    )
    goal = "Resolve every failure without human intervention when safely possible; "\
           "escalate clearly when not."
    # Note: orchestration is deterministic — no Claude call here.
    tools = ("geo_tool", "routing_tool", "twilio_tool", "db_write_tool", "spawn_agent",
             "db_read_tool", "notification_tool")

    def __init__(
        self,
        anthropic_client=None,
        *,
        dispatch: DispatchAgent | None = None,
        communication: CommunicationAgent | None = None,
    ) -> None:
        super().__init__(anthropic_client=anthropic_client)
        self.dispatch = dispatch or DispatchAgent(anthropic_client=anthropic_client)
        self.communication = communication or CommunicationAgent(anthropic_client=anthropic_client)

    async def _execute(self, context: AgentContext) -> EscalationOutcome:
        incident_id = context.incident_id
        if incident_id is None:
            raise AgentExecutionError("EscalationAgent requires context.incident_id")

        reason_raw = context.payload.get("reason")
        try:
            reason = EscalationReason(reason_raw)
        except (ValueError, TypeError) as exc:
            raise AgentExecutionError(
                f"unknown escalation reason: {reason_raw!r}. "
                f"Allowed: {[r.value for r in EscalationReason]}"
            ) from exc

        incident = await get_incident(context.db, incident_id)
        if incident is None:
            raise AgentExecutionError(f"incident {incident_id} not found")

        await self._log_step(
            context, TaskLogStatus.STARTED, step=f"escalation.{reason.value}",
            reasoning=f"escalation triggered for {incident_id}",
        )

        # Route to handler
        if reason == EscalationReason.NO_PROVIDER:
            return await self._handle_no_provider(context, incident)
        if reason in (EscalationReason.PROVIDER_OFFLINE, EscalationReason.STALLED_ASSIGNMENT):
            return await self._handle_redispatch_path(context, incident, reason)
        if reason == EscalationReason.STALLED_EN_ROUTE:
            return await self._handle_stalled_en_route(context, incident)
        if reason == EscalationReason.REPEATED_FAILURE:
            return await self._handle_repeated_failure(context, incident)
        # Unreachable — enum exhaustive
        raise AgentExecutionError(f"unhandled reason: {reason}")

    # ------------------------------------------------------------------
    # NO_PROVIDER
    # ------------------------------------------------------------------

    async def _handle_no_provider(self, context, incident) -> EscalationOutcome:
        if incident.status != IncidentStatus.NO_PROVIDER.value:
            try:
                await update_incident_status(
                    context.db, incident_id=incident.id,
                    new_status=IncidentStatus.NO_PROVIDER,
                    reason="escalation: no provider available",
                )
            except DbWriteError as exc:
                log.warning("no_provider_transition_failed", error=str(exc))

        admin_alerted = await self._alert_admins(
            context, incident,
            event_key="no_provider_alert",
            extra={"radius_used_km": context.payload.get("radius_used_km")},
        )
        await broadcast_incident_event(
            incident_id=incident.id,
            event="NO_PROVIDER_ALERT",
            agent=self.name,
            data={"radius_used_km": context.payload.get("radius_used_km")},
        )
        return EscalationOutcome(
            reason=EscalationReason.NO_PROVIDER.value,
            incident_id=incident.id,
            new_status=IncidentStatus.NO_PROVIDER.value,
            redispatched=False,
            new_provider_id=None,
            admin_alerted=admin_alerted,
            notes="No provider found; admin alerted.",
        )

    # ------------------------------------------------------------------
    # PROVIDER_OFFLINE / STALLED_ASSIGNMENT — release + redispatch
    # ------------------------------------------------------------------

    async def _handle_redispatch_path(
        self, context, incident, reason: EscalationReason,
    ) -> EscalationOutcome:
        if reason == EscalationReason.PROVIDER_OFFLINE:
            provider_offline_detections_total.inc()
        old_provider_id = incident.provider_id

        # 1. Release the old provider.
        # If they went offline, mark them unavailable so re-dispatch doesn't
        # immediately re-assign the same unreachable provider (infinite loop fix).
        if old_provider_id is not None:
            try:
                mark_available = reason != EscalationReason.PROVIDER_OFFLINE
                await release_provider_availability(
                    context.db,
                    provider_id=old_provider_id,
                    mark_available=mark_available,
                )
            except DbWriteError as exc:
                log.warning("release_old_provider_failed",
                            provider_id=str(old_provider_id), error=str(exc))

        # 2. Clear provider link and move to NO_PROVIDER so DispatchAgent can re-enter
        incident.provider_id = None
        try:
            await update_incident_status(
                context.db, incident_id=incident.id,
                new_status=IncidentStatus.NO_PROVIDER,
                reason=f"escalation: {reason.value}, redispatching",
            )
        except DbWriteError as exc:
            log.warning("status_transition_failed_during_escalation", error=str(exc))

        await broadcast_incident_event(
            incident_id=incident.id, event="STATUS_CHANGED", agent=self.name,
            data={"status": IncidentStatus.NO_PROVIDER.value,
                  "escalation_reason": reason.value},
        )

        # 3. Spawn DispatchAgent for a fresh search
        ai_diag = incident.ai_diagnosis or {}
        service_type = ai_diag.get("service_needed") if isinstance(ai_diag, dict) else None
        dispatch_ctx = AgentContext(
            db=context.db, incident_id=incident.id,
            payload={
                "lat": float(incident.lat),
                "lng": float(incident.lng),
                "service_type": service_type,
                "ai_diagnosis": ai_diag,
            },
        )
        dispatch_result = await self.dispatch.run(dispatch_ctx)
        result: DispatchResult | None = dispatch_result.output

        if result is not None and result.assigned:
            # Refresh to get the new status from DispatchAgent
            await context.db.refresh(incident)
            customer = await get_user(context.db, incident.customer_id)
            customer_notified = False
            if customer is not None:
                cust_ctx = AgentContext(
                    db=context.db, incident_id=incident.id,
                    payload={
                        "event": "provider_assigned",
                        "to_phone": customer.phone,
                        "context_data": {
                            "provider_name": result.provider_name,
                            "eta_minutes": result.eta_minutes,
                            "distance_km": result.distance_km,
                            "note": f"Reassigned after {reason.value.lower()}.",
                        },
                    },
                )
                cust_res = await self.communication.run(cust_ctx)
                customer_notified = bool(cust_res.output and cust_res.output.sent)
            return EscalationOutcome(
                reason=reason.value,
                incident_id=incident.id,
                new_status=incident.status,
                redispatched=True,
                new_provider_id=result.provider_id,
                admin_alerted=False,
                notes=(
                    f"Re-dispatched to {result.provider_name} "
                    f"({result.distance_km:.2f} km, ETA {result.eta_minutes} min). "
                    f"Customer notified: {customer_notified}."
                ),
            )

        # 4. Redispatch failed — fall through to admin alert
        admin_alerted = await self._alert_admins(
            context, incident,
            event_key="no_provider_alert",
            extra={
                "escalation_reason": reason.value,
                "previous_provider_id": str(old_provider_id) if old_provider_id else None,
            },
        )
        return EscalationOutcome(
            reason=reason.value,
            incident_id=incident.id,
            new_status=IncidentStatus.NO_PROVIDER.value,
            redispatched=False,
            new_provider_id=None,
            admin_alerted=admin_alerted,
            notes=(
                f"Re-dispatch after {reason.value} failed. "
                "Admin alerted for manual intervention."
            ),
        )

    # ------------------------------------------------------------------
    # STALLED_EN_ROUTE — alert only, don't reassign mid-trip
    # ------------------------------------------------------------------

    async def _handle_stalled_en_route(self, context, incident) -> EscalationOutcome:
        admin_alerted = await self._alert_admins(
            context, incident,
            event_key="custom",
            extra={"text": (
                f"INCIDENT {incident.id} has been EN_ROUTE longer than the timeout. "
                f"Provider may need contact; customer may be stranded. Address: "
                f"{incident.address or f'({incident.lat}, {incident.lng})'}."
            )},
        )
        await broadcast_incident_event(
            incident_id=incident.id, event="NO_PROVIDER_ALERT", agent=self.name,
            data={"sub_reason": EscalationReason.STALLED_EN_ROUTE.value},
        )
        return EscalationOutcome(
            reason=EscalationReason.STALLED_EN_ROUTE.value,
            incident_id=incident.id,
            new_status=incident.status,
            redispatched=False,
            new_provider_id=None,
            admin_alerted=admin_alerted,
            notes="EN_ROUTE timeout; admin alerted, provider not preempted.",
        )

    # ------------------------------------------------------------------
    # REPEATED_FAILURE — terminal escalation
    # ------------------------------------------------------------------

    async def _handle_repeated_failure(self, context, incident) -> EscalationOutcome:
        try:
            await update_incident_status(
                context.db, incident_id=incident.id,
                new_status=IncidentStatus.ESCALATED,
                reason="escalation: repeated agent failures",
            )
            incidents_escalated_total.inc()
        except DbWriteError as exc:
            log.warning("escalated_transition_failed", error=str(exc))

        await broadcast_incident_event(
            incident_id=incident.id, event="STATUS_CHANGED", agent=self.name,
            data={"status": IncidentStatus.ESCALATED.value,
                  "escalation_reason": EscalationReason.REPEATED_FAILURE.value},
        )

        summary = (
            context.payload.get("summary")
            or "Multiple agent failures while processing this incident. Manual review required."
        )
        admin_alerted = await self._alert_admins(
            context, incident,
            event_key="custom",
            extra={"text": f"ESCALATED incident {incident.id}: {summary}"},
        )
        return EscalationOutcome(
            reason=EscalationReason.REPEATED_FAILURE.value,
            incident_id=incident.id,
            new_status=IncidentStatus.ESCALATED.value,
            redispatched=False,
            new_provider_id=None,
            admin_alerted=admin_alerted,
            notes=f"Marked ESCALATED. Summary: {summary[:200]}",
        )

    # ------------------------------------------------------------------
    # Admin alert fan-out
    # ------------------------------------------------------------------

    async def _alert_admins(
        self, context, incident, *, event_key: str, extra: dict | None = None,
    ) -> bool:
        admins = await get_active_admins(context.db, limit=5)
        any_sent = False
        for admin in admins:
            ctx_data = {
                "address": incident.address or f"({incident.lat}, {incident.lng})",
                "incident_id": str(incident.id),
            }
            if extra:
                ctx_data.update({k: v for k, v in extra.items() if v is not None})

            alert_ctx = AgentContext(
                db=context.db, incident_id=incident.id,
                payload={
                    "event": event_key,
                    "to_phone": admin.phone,
                    "context_data": ctx_data,
                },
            )
            res = await self.communication.run(alert_ctx)
            if res.output and res.output.sent:
                any_sent = True
        return any_sent


# ----------------------------------------------------------------------
# Convenience wrapper
# ----------------------------------------------------------------------


async def escalate(
    *,
    db,
    incident_id: uuid.UUID,
    reason: EscalationReason,
    payload_extra: dict | None = None,
) -> EscalationOutcome | None:
    """One-call helper used by TrackingAgent and the OrchestratorAgent."""
    agent = EscalationAgent()
    payload = {"reason": reason.value}
    if payload_extra:
        payload.update(payload_extra)
    ctx = AgentContext(db=db, incident_id=incident_id, payload=payload)
    result = await agent.run(ctx)
    return result.output

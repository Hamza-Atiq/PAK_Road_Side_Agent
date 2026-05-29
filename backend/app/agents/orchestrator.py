"""OrchestratorAgent — the root coordinator.

Receives an incident ID, drives it through the full agent pipeline:

    Guardrail  →  Triage  →  Dispatch  →  Communication (× 2: customer + provider)
                                           ↘ (on failure)
                                              NO_PROVIDER → admin alert

This agent does NOT call Claude directly — it reasons in plain Python over
the sub-agent outputs. The "agentic" character comes from delegating to
specialized agents that DO reason. The orchestrator's job is consistent
execution, not creative reasoning.

Why deterministic orchestration
-------------------------------
Putting Claude in the orchestrator loop adds latency and a failure surface
without buying decision quality — the actual decisions live in the
sub-agents. Keeping this layer deterministic also makes the audit trail
(task_logs) easy to follow: every step name maps 1:1 to a code path.
"""
from __future__ import annotations

import time
import uuid
from dataclasses import dataclass

from app.agents.base import AgentContext, AgentExecutionError, BaseAgent
from app.agents.communication import CommunicationAgent
from app.agents.dispatch import DispatchAgent, DispatchResult
from app.agents.guardrail import GuardrailAgent, GuardrailDecision
from app.agents.triage import TriageAgent
from app.metrics import observe_incident_processing
from app.middleware.logging import get_logger
from app.models.enums import IncidentStatus, TaskLogStatus
from app.schemas.diagnosis import DiagnosisResult
from app.tools.db_read_tool import get_active_admins, get_incident, get_user
from app.tools.db_write_tool import update_incident_status
from app.tools.notification_tool import broadcast_incident_event

log = get_logger("agents.orchestrator")


# ----------------------------------------------------------------------
# Result
# ----------------------------------------------------------------------


@dataclass
class OrchestrationOutcome:
    incident_id: uuid.UUID
    final_status: str
    guardrail_safe: bool
    diagnosis: DiagnosisResult | None
    dispatch: DispatchResult | None
    customer_notified: bool
    provider_notified: bool
    admin_alerted: bool
    reasoning: str

    def to_dict(self) -> dict:
        return {
            "incident_id": str(self.incident_id),
            "final_status": self.final_status,
            "guardrail_safe": self.guardrail_safe,
            "diagnosis": self.diagnosis.model_dump(mode="json") if self.diagnosis else None,
            "dispatch": self.dispatch.to_dict() if self.dispatch else None,
            "customer_notified": self.customer_notified,
            "provider_notified": self.provider_notified,
            "admin_alerted": self.admin_alerted,
            "reasoning": self.reasoning[:1000],
        }


# ----------------------------------------------------------------------
# OrchestratorAgent
# ----------------------------------------------------------------------


class OrchestratorAgent(BaseAgent[OrchestrationOutcome]):
    name = "OrchestratorAgent"
    persona = (
        "Lead coordinator. Delegates every decision to a specialist agent and "
        "ensures the incident reaches a resolved state without stalling."
    )
    goal = "Resolve every incident end-to-end. Never let one stall in an intermediate state."
    # Reasoning layer — no Claude call required for orchestration itself
    tools = ("spawn_agent", "db_read_tool", "db_write_tool", "notification_tool")

    def __init__(
        self,
        anthropic_client=None,
        *,
        guardrail: GuardrailAgent | None = None,
        triage: TriageAgent | None = None,
        dispatch: DispatchAgent | None = None,
        communication: CommunicationAgent | None = None,
    ) -> None:
        super().__init__(anthropic_client=anthropic_client)
        # Sub-agents are injectable for testing; default to fresh instances
        # sharing the orchestrator's Anthropic client.
        self.guardrail = guardrail or GuardrailAgent(anthropic_client=anthropic_client)
        self.triage = triage or TriageAgent(anthropic_client=anthropic_client)
        self.dispatch = dispatch or DispatchAgent(anthropic_client=anthropic_client)
        self.communication = communication or CommunicationAgent(anthropic_client=anthropic_client)

    # ------------------------------------------------------------------
    # Main pipeline
    # ------------------------------------------------------------------

    async def _execute(self, context: AgentContext) -> OrchestrationOutcome:
        incident_id = context.incident_id
        if incident_id is None:
            raise AgentExecutionError("OrchestratorAgent requires context.incident_id")

        pipeline_start = time.perf_counter()
        incident = await get_incident(context.db, incident_id)
        if incident is None:
            raise AgentExecutionError(f"incident {incident_id} not found")

        customer = await get_user(context.db, incident.customer_id)
        if customer is None:
            raise AgentExecutionError(f"customer {incident.customer_id} not found")

        outcome = OrchestrationOutcome(
            incident_id=incident_id,
            final_status=incident.status,
            guardrail_safe=True,
            diagnosis=None,
            dispatch=None,
            customer_notified=False,
            provider_notified=False,
            admin_alerted=False,
            reasoning="",
        )

        # ===== Step 1: Guardrail on the description =====
        sanitized_description = await self._step_guardrail(context, incident, outcome)
        if not outcome.guardrail_safe:
            return outcome

        # ===== Step 2: ANALYZING =====
        await update_incident_status(
            context.db,
            incident_id=incident_id,
            new_status=IncidentStatus.ANALYZING,
            reason="orchestrator started analysis",
        )
        await broadcast_incident_event(
            incident_id=incident_id,
            event="STATUS_CHANGED",
            agent=self.name,
            data={"status": IncidentStatus.ANALYZING.value},
        )

        # ===== Step 3: Triage =====
        diagnosis = await self._step_triage(
            context,
            incident,
            sanitized_description=sanitized_description,
            outcome=outcome,
        )
        outcome.diagnosis = diagnosis

        # ===== Step 4: Dispatch =====
        dispatch_result = await self._step_dispatch(
            context, incident, diagnosis=diagnosis, outcome=outcome
        )
        outcome.dispatch = dispatch_result

        # ===== Step 5: Outcome-driven notifications =====
        if dispatch_result.assigned:
            await self._step_notify_success(context, incident, customer, dispatch_result, outcome)
        else:
            await self._step_handle_no_provider(context, incident, outcome)

        # Refresh final status for the outcome
        await context.db.refresh(incident)
        outcome.final_status = incident.status

        # Observe end-to-end REPORTED → ASSIGNED latency on successful dispatch
        if dispatch_result.assigned:
            observe_incident_processing(time.perf_counter() - pipeline_start)

        return outcome

    # ------------------------------------------------------------------
    # Step helpers
    # ------------------------------------------------------------------

    async def _step_guardrail(
        self, context: AgentContext, incident, outcome: OrchestrationOutcome,
    ) -> str:
        """Run the Guardrail on the incident description. Returns sanitized text.

        On unsafe: mark incident.guardrail_flagged + CLOSED + return early via outcome.
        """
        raw_text = (incident.description or "").strip()
        if not raw_text:
            # No description to screen — proceed with empty sanitized text
            return ""

        guardrail_ctx = AgentContext(
            db=context.db,
            incident_id=incident.id,
            user_id=incident.customer_id,
            payload={"raw_input": raw_text},
            metadata=context.metadata,
        )
        result = await self.guardrail.run(guardrail_ctx)
        decision: GuardrailDecision | None = result.output

        if decision is None or not decision.safe:
            # Mark incident closed and flagged
            incident.guardrail_flagged = True
            await update_incident_status(
                context.db,
                incident_id=incident.id,
                new_status=IncidentStatus.CLOSED,
                reason="guardrail blocked input",
            )
            outcome.guardrail_safe = False
            outcome.final_status = IncidentStatus.CLOSED.value
            outcome.reasoning = (
                f"GuardrailAgent flagged the input as unsafe: "
                f"{decision.reason if decision else 'guardrail run failed'}"
            )
            await self._log_step(
                context, TaskLogStatus.FAILURE, step="guardrail_blocked",
                reasoning=outcome.reasoning,
                payload={"patterns": decision.flagged_patterns if decision else []},
            )
            await broadcast_incident_event(
                incident_id=incident.id,
                event="STATUS_CHANGED",
                agent=self.name,
                data={"status": IncidentStatus.CLOSED.value, "reason": "guardrail"},
            )
            return ""

        return decision.sanitized

    async def _step_triage(
        self,
        context: AgentContext,
        incident,
        *,
        sanitized_description: str,
        outcome: OrchestrationOutcome,
    ) -> DiagnosisResult:
        triage_ctx = AgentContext(
            db=context.db,
            incident_id=incident.id,
            payload={
                "description": sanitized_description or None,
                "image_url": incident.image_url,
                "voice_url": incident.voice_url,
            },
        )
        result = await self.triage.run(triage_ctx)
        if result.output is None:
            # Triage failed entirely — produce a minimal unknown diagnosis so the
            # dispatch step can still attempt a generalist provider.
            from app.models.enums import IncidentSeverity, ServiceType
            unknown = DiagnosisResult(
                issue_type="unknown",
                severity=IncidentSeverity.unknown,
                service_needed=ServiceType.other,
                confidence=0.0,
                details=f"triage failed: {result.error}",
            )
            outcome.reasoning += f"triage failed ({result.error}); proceeding with unknown. "
            return unknown
        return result.output

    async def _step_dispatch(
        self,
        context: AgentContext,
        incident,
        *,
        diagnosis: DiagnosisResult,
        outcome: OrchestrationOutcome,
    ) -> DispatchResult:
        dispatch_ctx = AgentContext(
            db=context.db,
            incident_id=incident.id,
            payload={
                "lat": float(incident.lat),
                "lng": float(incident.lng),
                "service_type": diagnosis.service_needed,
                "ai_diagnosis": diagnosis.model_dump(mode="json"),
            },
        )
        result = await self.dispatch.run(dispatch_ctx)
        if result.output is None:
            outcome.reasoning += f"dispatch run errored: {result.error}. "
            return DispatchResult(assigned=False, reasoning=result.error or "dispatch run failed")
        return result.output

    async def _step_notify_success(
        self,
        context: AgentContext,
        incident,
        customer,
        dispatch: DispatchResult,
        outcome: OrchestrationOutcome,
    ) -> None:
        """Two outbound messages: customer 'provider on the way' + provider 'new job offer'."""
        # Customer
        cust_ctx = AgentContext(
            db=context.db,
            incident_id=incident.id,
            payload={
                "event": "provider_assigned",
                "to_phone": customer.phone,
                "context_data": {
                    "provider_name": dispatch.provider_name,
                    "eta_minutes": dispatch.eta_minutes,
                    "distance_km": dispatch.distance_km,
                },
            },
        )
        cust_result = await self.communication.run(cust_ctx)
        outcome.customer_notified = bool(cust_result.output and cust_result.output.sent)

        # Provider
        provider_user = await get_user(context.db, dispatch.provider_id) if dispatch.provider_id else None
        if provider_user is not None:
            prov_ctx = AgentContext(
                db=context.db,
                incident_id=incident.id,
                payload={
                    "event": "new_job_offer",
                    "to_phone": provider_user.phone,
                    "context_data": {
                        "address": incident.address or f"({incident.lat}, {incident.lng})",
                        "distance_km": dispatch.distance_km,
                        "eta_minutes": dispatch.eta_minutes,
                        "ai_diagnosis": (
                            outcome.diagnosis.issue_type if outcome.diagnosis else None
                        ),
                    },
                },
            )
            prov_result = await self.communication.run(prov_ctx)
            outcome.provider_notified = bool(prov_result.output and prov_result.output.sent)

        outcome.reasoning += (
            f"Assigned {dispatch.provider_name} ({dispatch.distance_km:.2f} km, "
            f"ETA {dispatch.eta_minutes} min). Customer notified: {outcome.customer_notified}. "
            f"Provider notified: {outcome.provider_notified}."
        )

    async def _step_handle_no_provider(
        self,
        context: AgentContext,
        incident,
        outcome: OrchestrationOutcome,
    ) -> None:
        """No provider was found; move to NO_PROVIDER and notify any active admin.

        Phase 9's EscalationAgent will replace/extend this with multi-attempt
        recovery (radius expansion is already in DispatchAgent; here we'd add
        cross-service-type retries and human-dispatcher hand-off).
        """
        await update_incident_status(
            context.db,
            incident_id=incident.id,
            new_status=IncidentStatus.NO_PROVIDER,
            reason="no available provider after dispatch expansion",
        )
        await broadcast_incident_event(
            incident_id=incident.id,
            event="NO_PROVIDER_ALERT",
            agent=self.name,
            data={"radius_used_km": outcome.dispatch.radius_used_km if outcome.dispatch else None},
        )

        admins = await get_active_admins(context.db, limit=3)
        for admin in admins:
            alert_ctx = AgentContext(
                db=context.db,
                incident_id=incident.id,
                payload={
                    "event": "no_provider_alert",
                    "to_phone": admin.phone,
                    "context_data": {
                        "address": incident.address or f"({incident.lat}, {incident.lng})",
                        "radius_used_km": (
                            outcome.dispatch.radius_used_km if outcome.dispatch else None
                        ),
                    },
                },
            )
            res = await self.communication.run(alert_ctx)
            if res.output and res.output.sent:
                outcome.admin_alerted = True

        outcome.reasoning += (
            "No provider available after radius expansion. "
            f"Status set to NO_PROVIDER. Admin alerted: {outcome.admin_alerted}."
        )


# ----------------------------------------------------------------------
# Convenience wrapper used by the Celery task
# ----------------------------------------------------------------------


async def process_incident(
    *,
    db,
    incident_id: uuid.UUID,
    anthropic_client=None,
) -> OrchestrationOutcome:
    """One-call entry point — used by the Celery task and tests."""
    agent = OrchestratorAgent(anthropic_client=anthropic_client)
    ctx = AgentContext(db=db, incident_id=incident_id)
    result = await agent.run(ctx)
    if result.output is not None:
        return result.output
    raise RuntimeError(result.error or "orchestrator run failed")

"""AdminAgent — natural-language admin queries and safe overrides.

Design
------
The agent never executes free-form code or SQL. It does two Claude calls:

  1. **Intent classification**: turn "show me stalled incidents from today"
     into `{"intent": "query_incidents", "params": {"status_in": [...], "since_hours": 24}}`.
  2. **Result summary**: turn the deterministic Python result into a friendly
     one-paragraph reply.

Between the two calls, only pre-approved Python handlers run — each one takes
a small typed param dict and reads/writes through the existing tools. This
keeps the surface narrow and auditable.

Supported intents
-----------------
- `query_incidents`           — filter by status, age, customer, provider
- `query_providers`           — filter by availability, approval, service
- `query_metrics`             — dashboard-style aggregates
- `reassign_incident`         — spawn DispatchAgent on an existing incident
- `suspend_provider`          — mark provider inactive + unavailable
- `notify_user`               — send a manual SMS via CommunicationAgent
- `unknown`                   — admin gets a helpful refusal
"""
from __future__ import annotations

import json
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any, Literal

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.base import AgentContext, AgentExecutionError, BaseAgent
from app.agents.communication import CommunicationAgent, CommunicationResult
from app.agents.dispatch import DispatchAgent, DispatchResult
from app.middleware.logging import get_logger
from app.models.enums import IncidentStatus, TaskLogStatus
from app.models.incident import Incident
from app.models.message import Message
from app.models.provider import Provider
from app.models.user import User
from app.tools.db_read_tool import get_incident, get_provider, get_user
from app.tools.db_write_tool import (
    DbWriteError,
    release_provider_availability,
    update_incident_status,
)

log = get_logger("agents.admin")

Intent = Literal[
    "query_incidents",
    "query_providers",
    "query_metrics",
    "reassign_incident",
    "suspend_provider",
    "notify_user",
    "unknown",
]

ALLOWED_INTENTS: set[str] = {
    "query_incidents", "query_providers", "query_metrics",
    "reassign_incident", "suspend_provider", "notify_user", "unknown",
}


# ----------------------------------------------------------------------
# Output
# ----------------------------------------------------------------------


@dataclass
class AdminAgentOutcome:
    intent: str
    summary: str
    data: dict[str, Any] = field(default_factory=dict)
    actioned: bool = False  # True when the agent mutated state

    def to_dict(self) -> dict:
        return {
            "intent": self.intent,
            "summary": self.summary[:1000],
            "data": self.data,
            "actioned": self.actioned,
        }


# ----------------------------------------------------------------------
# Prompts
# ----------------------------------------------------------------------


def _intent_system_prompt() -> str:
    return f"""You are an admin-query classifier for a roadside-assistance platform.

Read the admin's plain-English request and emit a JSON intent description.

Allowed intents:
- query_incidents      params: {{status_in?: [...], since_hours?: int, customer_phone?: str, provider_id?: uuid}}
- query_providers      params: {{is_available?: bool, is_approved?: bool, service_type?: str}}
- query_metrics        params: {{}} (always returns dashboard-style aggregates)
- reassign_incident    params: {{incident_id: uuid, new_provider_id?: uuid (optional, agent picks if omitted)}}
- suspend_provider     params: {{provider_id: uuid, reason?: str}}
- notify_user          params: {{to_phone: str (E.164), body: str}}
- unknown              params: {{}} (use when the request is ambiguous, unsafe, or not supported)

Status values: REPORTED, ANALYZING, ASSIGNED, NO_PROVIDER, ESCALATED, EN_ROUTE, ARRIVED, COMPLETED, CLOSED

Output ONLY this JSON, no prose:
{{"intent": "<intent>", "params": {{...}}}}

If the request mentions specific UUIDs, copy them verbatim. If it doesn't contain
required fields for an action intent, use `unknown`. If in doubt, use `unknown`.
"""


def _summary_system_prompt() -> str:
    return """You summarize structured query results for a platform admin. One short paragraph.
No markdown, no bullet points, plain text only. Lead with the headline number or fact.
If the result is empty, say so plainly. Maximum 500 characters."""


# ----------------------------------------------------------------------
# AdminAgent
# ----------------------------------------------------------------------


class AdminAgent(BaseAgent[AdminAgentOutcome]):
    name = "AdminAgent"
    persona = (
        "Knowledgeable platform analyst. Understands the dispatch pipeline end-to-end. "
        "Cautious with destructive operations — always confirms scope before acting."
    )
    goal = "Answer admin questions accurately. Execute safe overrides. Refuse anything ambiguous."
    max_tokens = 600
    tools = ("db_read_tool", "db_write_tool", "twilio_tool", "spawn_agent",
             "notification_tool")

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

    async def _execute(self, context: AgentContext) -> AdminAgentOutcome:
        query = context.payload.get("query")
        if not isinstance(query, str) or not query.strip():
            raise AgentExecutionError("AdminAgent requires payload['query'] (non-empty string)")

        intent, params = await self._classify_intent(query)

        await self._log_step(
            context, TaskLogStatus.STARTED, step=f"intent.{intent}",
            payload={"params_keys": list(params.keys())},
        )

        if intent == "query_incidents":
            data = await self._query_incidents(context.db, params)
        elif intent == "query_providers":
            data = await self._query_providers(context.db, params)
        elif intent == "query_metrics":
            data = await self._query_metrics(context.db)
        elif intent == "reassign_incident":
            data = await self._reassign_incident(context, params)
        elif intent == "suspend_provider":
            data = await self._suspend_provider(context.db, params)
        elif intent == "notify_user":
            data = await self._notify_user(context, params)
        else:
            data = {"message": "Request not recognized or unsupported."}
            return AdminAgentOutcome(intent="unknown", summary=data["message"], data=data)

        summary = await self._summarize(query, intent, data)
        actioned = intent in {"reassign_incident", "suspend_provider", "notify_user"}
        return AdminAgentOutcome(intent=intent, summary=summary, data=data, actioned=actioned)

    # ------------------------------------------------------------------
    # Intent classification
    # ------------------------------------------------------------------

    async def _classify_intent(self, query: str) -> tuple[str, dict[str, Any]]:
        try:
            raw = await self._call_claude(
                system=_intent_system_prompt(),
                messages=[{"role": "user", "content": query}],
                max_tokens=400,
                temperature=0.0,
            )
        except Exception as exc:  # noqa: BLE001
            log.warning("intent_classification_failed", error=str(exc))
            return "unknown", {}

        return _parse_intent(raw)

    # ------------------------------------------------------------------
    # Handlers — read intents
    # ------------------------------------------------------------------

    @staticmethod
    async def _query_incidents(db: AsyncSession, params: dict) -> dict:
        stmt = select(Incident)
        status_in = params.get("status_in")
        if isinstance(status_in, list) and status_in:
            valid = [s for s in status_in if s in {x.value for x in IncidentStatus}]
            if valid:
                stmt = stmt.where(Incident.status.in_(valid))

        since_hours = params.get("since_hours")
        if isinstance(since_hours, (int, float)) and since_hours > 0:
            cutoff = datetime.now(UTC) - timedelta(hours=int(since_hours))
            stmt = stmt.where(Incident.created_at >= cutoff)

        customer_phone = params.get("customer_phone")
        if isinstance(customer_phone, str) and customer_phone:
            customer_id = await db.scalar(
                select(User.id).where(User.phone == customer_phone)
            )
            if customer_id:
                stmt = stmt.where(Incident.customer_id == customer_id)

        provider_id = params.get("provider_id")
        if provider_id:
            try:
                stmt = stmt.where(Incident.provider_id == uuid.UUID(str(provider_id)))
            except (ValueError, TypeError):
                pass

        stmt = stmt.order_by(Incident.created_at.desc()).limit(25)
        rows = list((await db.execute(stmt)).scalars())
        return {
            "count": len(rows),
            "incidents": [
                {
                    "id": str(r.id), "status": r.status,
                    "lat": float(r.lat), "lng": float(r.lng),
                    "provider_id": str(r.provider_id) if r.provider_id else None,
                    "created_at": r.created_at.isoformat(),
                }
                for r in rows
            ],
        }

    @staticmethod
    async def _query_providers(db: AsyncSession, params: dict) -> dict:
        stmt = select(Provider, User).join(User, User.id == Provider.id)
        if isinstance(params.get("is_available"), bool):
            stmt = stmt.where(Provider.is_available.is_(params["is_available"]))
        if isinstance(params.get("is_approved"), bool):
            stmt = stmt.where(Provider.is_approved.is_(params["is_approved"]))
        svc = params.get("service_type")
        if isinstance(svc, str) and svc:
            stmt = stmt.where(Provider.service_type == svc)
        stmt = stmt.order_by(Provider.total_jobs.desc()).limit(50)
        rows = (await db.execute(stmt)).all()
        return {
            "count": len(rows),
            "providers": [
                {
                    "id": str(p.id), "name": u.name, "phone": u.phone,
                    "service_type": p.service_type,
                    "is_available": p.is_available,
                    "is_approved": p.is_approved,
                    "total_jobs": p.total_jobs,
                    "last_ping": p.last_ping.isoformat() if p.last_ping else None,
                }
                for (p, u) in rows
            ],
        }

    @staticmethod
    async def _query_metrics(db: AsyncSession) -> dict:
        # Dashboard-style aggregates — also reused by the /api/admin/dashboard endpoint
        return await build_dashboard_payload(db)

    # ------------------------------------------------------------------
    # Handlers — write intents
    # ------------------------------------------------------------------

    async def _reassign_incident(self, context: AgentContext, params: dict) -> dict:
        try:
            incident_id = uuid.UUID(str(params["incident_id"]))
        except (KeyError, ValueError, TypeError):
            return {"error": "incident_id missing or invalid"}

        incident = await get_incident(context.db, incident_id)
        if incident is None:
            return {"error": f"incident {incident_id} not found"}

        # Release old provider if present
        if incident.provider_id is not None:
            try:
                await release_provider_availability(context.db, provider_id=incident.provider_id)
            except DbWriteError as exc:
                log.warning("release_failed_during_reassign", error=str(exc))

        # Move to NO_PROVIDER so DispatchAgent can transition to ASSIGNED again
        try:
            await update_incident_status(
                context.db, incident_id=incident.id,
                new_status=IncidentStatus.NO_PROVIDER,
                reason="admin reassign requested",
            )
        except DbWriteError as exc:
            return {"error": f"could not reset incident status: {exc}"}

        incident.provider_id = None
        await context.db.flush()

        ai_diag = incident.ai_diagnosis or {}
        service_type = ai_diag.get("service_needed") if isinstance(ai_diag, dict) else None

        # Run DispatchAgent
        dispatch_ctx = AgentContext(
            db=context.db, incident_id=incident.id,
            payload={
                "lat": float(incident.lat), "lng": float(incident.lng),
                "service_type": service_type, "ai_diagnosis": ai_diag,
            },
        )
        result = await self.dispatch.run(dispatch_ctx)
        d: DispatchResult | None = result.output
        if d is None or not d.assigned:
            return {
                "incident_id": str(incident.id),
                "reassigned": False,
                "reason": d.reasoning if d else (result.error or "dispatch failed"),
            }
        return {
            "incident_id": str(incident.id),
            "reassigned": True,
            "new_provider_id": str(d.provider_id),
            "new_provider_name": d.provider_name,
            "eta_minutes": d.eta_minutes,
            "distance_km": d.distance_km,
            "rationale": d.reasoning,
        }

    async def _suspend_provider(self, db: AsyncSession, params: dict) -> dict:
        try:
            provider_id = uuid.UUID(str(params["provider_id"]))
        except (KeyError, ValueError, TypeError):
            return {"error": "provider_id missing or invalid"}

        user = await get_user(db, provider_id)
        if user is None or user.role != "provider":
            return {"error": f"no provider user with id {provider_id}"}
        provider = await get_provider(db, provider_id)
        if provider is None:
            return {"error": f"no provider profile with id {provider_id}"}

        user.is_active = False
        provider.is_available = False
        await db.flush()
        return {
            "provider_id": str(provider_id),
            "suspended": True,
            "reason": params.get("reason") or "admin action",
        }

    async def _notify_user(self, context: AgentContext, params: dict) -> dict:
        to_phone = params.get("to_phone")
        body = params.get("body")
        if not to_phone or not body:
            return {"error": "to_phone and body are required"}

        notify_ctx = AgentContext(
            db=context.db, incident_id=context.incident_id,
            payload={
                "event": "custom",
                "to_phone": to_phone,
                "content_override": body,
                "context_data": {},
            },
        )
        result = await self.communication.run(notify_ctx)
        comm: CommunicationResult | None = result.output
        if comm is None or not comm.sent:
            return {"sent": False, "reason": (comm.reason if comm else result.error)}
        return {
            "sent": True,
            "message_id": str(comm.message_id),
            "twilio_sid": comm.twilio_sid,
            "channel": comm.channel,
        }

    # ------------------------------------------------------------------
    # Summary
    # ------------------------------------------------------------------

    async def _summarize(self, original_query: str, intent: str, data: dict) -> str:
        """Compose a one-paragraph plain-text reply to the admin."""
        # Cheap path: if the data already contains an explicit error, just echo it
        if isinstance(data, dict) and data.get("error"):
            return f"Couldn't complete the request: {data['error']}"

        prompt = (
            f"Admin asked: {original_query}\n"
            f"Intent: {intent}\n"
            f"Result data (JSON): {json.dumps(data, default=str)[:2000]}\n"
            "Write the reply now."
        )
        try:
            text = await self._call_claude(
                system=_summary_system_prompt(),
                messages=[{"role": "user", "content": prompt}],
                max_tokens=300,
                temperature=0.2,
            )
        except Exception as exc:  # noqa: BLE001
            log.warning("summary_call_failed_using_fallback", error=str(exc))
            return _deterministic_summary(intent, data)
        return text.strip()[:500] or _deterministic_summary(intent, data)


# ----------------------------------------------------------------------
# Intent parser (pure, testable)
# ----------------------------------------------------------------------


def _parse_intent(raw: str) -> tuple[str, dict[str, Any]]:
    """Parse Claude's JSON intent emission. Fail-safe: returns ('unknown', {})."""
    if not raw:
        return "unknown", {}

    cleaned = raw.strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.split("\n", 1)[1] if "\n" in cleaned else cleaned[3:]
    if cleaned.endswith("```"):
        cleaned = cleaned.rsplit("```", 1)[0].strip()

    try:
        data = json.loads(cleaned)
    except json.JSONDecodeError:
        return "unknown", {}

    if not isinstance(data, dict):
        return "unknown", {}

    intent = data.get("intent")
    params = data.get("params") or {}
    if intent not in ALLOWED_INTENTS or not isinstance(params, dict):
        return "unknown", {}
    return intent, params


# ----------------------------------------------------------------------
# Deterministic fallback summary
# ----------------------------------------------------------------------


def _deterministic_summary(intent: str, data: dict) -> str:
    if intent == "query_incidents":
        return f"Found {data.get('count', 0)} incidents matching the filter."
    if intent == "query_providers":
        return f"Found {data.get('count', 0)} providers matching the filter."
    if intent == "query_metrics":
        return "Dashboard snapshot retrieved."
    if intent == "reassign_incident":
        return (
            f"Reassigned to {data.get('new_provider_name', 'a new provider')}."
            if data.get("reassigned") else
            f"Reassignment failed: {data.get('reason', 'no provider available')}."
        )
    if intent == "suspend_provider":
        return f"Provider {data.get('provider_id', '?')} suspended."
    if intent == "notify_user":
        return f"Message sent (sid={data.get('twilio_sid')})." if data.get("sent") \
            else f"Message not sent: {data.get('reason', 'unknown error')}"
    return "Request not recognized."


# ----------------------------------------------------------------------
# Dashboard aggregator — reused by /api/admin/dashboard
# ----------------------------------------------------------------------


async def build_dashboard_payload(db: AsyncSession) -> dict:
    """Snapshot of platform state. Used by AdminAgent and the dashboard endpoint."""
    now = datetime.now(UTC)
    day_ago = now - timedelta(hours=24)
    ping_cutoff = now - timedelta(seconds=90)

    # Incidents grouped by status
    by_status = {s.value: 0 for s in IncidentStatus}
    rows = await db.execute(
        select(Incident.status, func.count(Incident.id)).group_by(Incident.status)
    )
    for status_value, count in rows:
        by_status[status_value] = int(count)

    incidents_24h = int(await db.scalar(
        select(func.count(Incident.id)).where(Incident.created_at >= day_ago)
    ) or 0)

    open_incidents = (
        by_status.get("REPORTED", 0) + by_status.get("ANALYZING", 0)
        + by_status.get("ASSIGNED", 0) + by_status.get("EN_ROUTE", 0)
        + by_status.get("ARRIVED", 0) + by_status.get("NO_PROVIDER", 0)
    )

    # Providers
    total_approved = int(await db.scalar(
        select(func.count(Provider.id)).where(Provider.is_approved.is_(True))
    ) or 0)
    available_now = int(await db.scalar(
        select(func.count(Provider.id))
        .where(Provider.is_approved.is_(True)).where(Provider.is_available.is_(True))
    ) or 0)
    online_pingers = int(await db.scalar(
        select(func.count(Provider.id)).where(Provider.last_ping >= ping_cutoff)
    ) or 0)
    on_active_job = int(await db.scalar(
        select(func.count(Incident.id.distinct()))
        .where(Incident.status.in_([
            IncidentStatus.ASSIGNED.value,
            IncidentStatus.EN_ROUTE.value,
            IncidentStatus.ARRIVED.value,
        ]))
    ) or 0)

    # Messaging
    total_msgs = int(await db.scalar(
        select(func.count(Message.id)).where(Message.created_at >= day_ago)
    ) or 0)
    delivered_msgs = int(await db.scalar(
        select(func.count(Message.id))
        .where(Message.created_at >= day_ago)
        .where(Message.delivery_status == "DELIVERED")
    ) or 0)
    failed_msgs = int(await db.scalar(
        select(func.count(Message.id))
        .where(Message.created_at >= day_ago)
        .where(Message.delivery_status == "FAILED")
    ) or 0)
    delivery_rate = (delivered_msgs / total_msgs) if total_msgs > 0 else 1.0

    # Avg ETA in last 24h
    avg_eta = await db.scalar(
        select(func.avg(Incident.eta_minutes))
        .where(Incident.created_at >= day_ago)
        .where(Incident.eta_minutes.is_not(None))
    )
    avg_eta_value = float(avg_eta) if avg_eta is not None else None

    return {
        "incidents_by_status": by_status,
        "incident_counts_24h": incidents_24h,
        "providers": {
            "total_approved": total_approved,
            "available_now": available_now,
            "online_pingers": online_pingers,
            "on_active_job": on_active_job,
        },
        "messaging": {
            "total_24h": total_msgs,
            "delivered_24h": delivered_msgs,
            "failed_24h": failed_msgs,
            "delivery_rate": round(delivery_rate, 4),
        },
        "open_incidents_count": open_incidents,
        "avg_eta_minutes_24h": avg_eta_value,
        "generated_at": now.isoformat(),
    }

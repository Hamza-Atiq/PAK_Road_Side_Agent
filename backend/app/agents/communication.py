"""CommunicationAgent — every customer-facing and provider-facing message.

Inputs (via AgentContext.payload):
    - event: str          — one of EVENT_KEYS below
    - to_phone: str       — E.164 recipient
    - channel: str        — "sms" | "whatsapp" (default sms)
    - context_data: dict  — event-specific facts the model uses to compose the message
                            (provider_name, eta_minutes, address, etc.)

Output: CommunicationResult { sent: bool, message_id: UUID | None, channel: str,
                              twilio_sid: str | None, content: str, reason: str }

Behavior:
- Generates message text via Claude, NOT fixed templates — different cultures
  and contexts read differently and the model adapts tone.
- Sends through twilio_tool.send_message which persists the row.
- Also broadcasts a MESSAGE_SENT WebSocket event so the in-app UI sees the same
  thing the customer/provider saw via SMS.
- Cannot mutate incident/provider state — tool allow-list is strict.

WhatsApp fallback for FAILED deliveries happens asynchronously via the Twilio
status-callback webhook (Phase 7.5), not by this agent.
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Literal

from app.agents.base import AgentContext, AgentExecutionError, BaseAgent
from app.middleware.logging import get_logger
from app.models.enums import MessageType
from app.services.twilio_service import TwilioSendError
from app.tools.notification_tool import broadcast_incident_event
from app.tools.twilio_tool import send_message

log = get_logger("agents.communication")

Channel = Literal["sms", "whatsapp"]

# Canonical event labels the orchestrator passes in. Keeps the surface narrow.
EVENT_KEYS = {
    "provider_assigned",    # → customer
    "en_route",             # → customer
    "arrived",              # → customer
    "completed",            # → customer
    "new_job_offer",        # → provider
    "no_provider_alert",    # → admin or customer
    "custom",               # → free-form, content_override required
}


@dataclass
class CommunicationResult:
    sent: bool
    message_id: uuid.UUID | None = None
    channel: Channel = "sms"
    twilio_sid: str | None = None
    content: str = ""
    reason: str = ""

    def to_dict(self) -> dict:
        return {
            "sent": self.sent,
            "message_id": str(self.message_id) if self.message_id else None,
            "channel": self.channel,
            "twilio_sid": self.twilio_sid,
            "content_preview": self.content[:120],
            "reason": self.reason,
        }


# ----------------------------------------------------------------------
# System prompt for message generation
# ----------------------------------------------------------------------


_SYSTEM_PROMPT = """You write short, clear SMS messages on behalf of a global roadside-assistance platform.

Audience: a real driver or service provider, on their phone, in a stressful moment.

Rules:
- Keep it under 320 characters (2 SMS segments max).
- Plain text only — no markdown, no emojis.
- Lead with the actionable fact (who/when/what).
- Friendly and reassuring, never robotic or template-ish.
- Never reveal internal IDs, agent names, system internals.
- If the event is `new_job_offer`, end with: "Reply YES to accept or NO to decline."
- If the event is `no_provider_alert`, escalate clearly so the admin sees urgency.

Output ONLY the SMS body text. No quotes, no preamble, no JSON, no explanation.
"""


def _compose_user_prompt(event: str, data: dict) -> str:
    """Render the event context into a clear prompt for Claude."""
    lines = [f"Event: {event}", "Context facts:"]
    for k, v in data.items():
        if v is None:
            continue
        lines.append(f"- {k}: {v}")
    return "\n".join(lines)


# ----------------------------------------------------------------------
# CommunicationAgent
# ----------------------------------------------------------------------


class CommunicationAgent(BaseAgent[CommunicationResult]):
    name = "CommunicationAgent"
    persona = (
        "Empathetic communicator. Writes the way a calm, experienced dispatcher would "
        "text a stranded customer — short, warm, specific. Never reveals internals."
    )
    goal = "Keep every stakeholder informed at the right moment with the right tone."
    max_tokens = 300
    # Strictly send + broadcast. No incident or provider writes.
    tools = ("twilio_tool", "notification_tool")

    async def _execute(self, context: AgentContext) -> CommunicationResult:
        payload = context.payload
        event = payload.get("event")
        to_phone = payload.get("to_phone")
        channel: Channel = payload.get("channel", "sms")
        context_data = payload.get("context_data") or {}
        content_override: str | None = payload.get("content_override")

        if event not in EVENT_KEYS:
            raise AgentExecutionError(
                f"unknown event '{event}'. Must be one of {sorted(EVENT_KEYS)}"
            )
        if not to_phone:
            raise AgentExecutionError("to_phone is required")
        if channel not in ("sms", "whatsapp"):
            raise AgentExecutionError(f"unsupported channel: {channel}")

        # ----- Generate message text -----
        if content_override:
            content = content_override.strip()
        else:
            content = await self._generate_content(event, context_data)

        if not content:
            return CommunicationResult(
                sent=False, channel=channel,
                reason="generated message was empty",
            )

        # ----- Send via Twilio + persist row -----
        self._check_tool_authorized("twilio_tool")
        try:
            row = await send_message(
                context.db,
                to_phone=to_phone,
                body=content,
                channel=channel,
                incident_id=context.incident_id,
                sender_agent=self.name,
            )
        except TwilioSendError as exc:
            return CommunicationResult(
                sent=False, channel=channel, content=content,
                reason=f"twilio send failed: {exc}",
            )

        # ----- Broadcast to in-app subscribers -----
        if context.incident_id is not None:
            self._check_tool_authorized("notification_tool")
            await broadcast_incident_event(
                incident_id=context.incident_id,
                event="MESSAGE_SENT",
                agent=self.name,
                data={
                    "channel": row.msg_type,
                    "recipient": to_phone,
                    "preview": content[:200],
                    "event_key": event,
                },
            )

        return CommunicationResult(
            sent=True,
            message_id=row.id,
            channel=channel,
            twilio_sid=row.twilio_sid,
            content=content,
            reason="ok",
        )

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    async def _generate_content(self, event: str, data: dict) -> str:
        """Ask Claude to compose the SMS body. Returns plain text (no quotes, no JSON)."""
        user_prompt = _compose_user_prompt(event, data)
        try:
            text = await self._call_claude(
                system=_SYSTEM_PROMPT,
                messages=[{"role": "user", "content": user_prompt}],
                max_tokens=self.max_tokens,
                temperature=0.3,  # a touch of variation across calls is OK for tone
            )
        except Exception as exc:  # noqa: BLE001
            # NB: structlog reserves the kwarg name `event`; use `event_key` instead.
            log.warning(
                "comm_generate_failed_using_fallback",
                event_key=event,
                error=str(exc),
            )
            return _fallback_message(event, data)

        text = text.strip()
        # Strip wrapping quotes if model added them
        if (text.startswith('"') and text.endswith('"')) or (
            text.startswith("'") and text.endswith("'")
        ):
            text = text[1:-1].strip()
        return text[:320]  # hard cap to fit 2 SMS segments


# ----------------------------------------------------------------------
# Deterministic fallback messages — used only when Claude is unreachable
# ----------------------------------------------------------------------


def _fallback_message(event: str, data: dict) -> str:
    provider = data.get("provider_name", "your provider")
    eta = data.get("eta_minutes")
    addr = data.get("address", "your location")
    fallbacks = {
        "provider_assigned": (
            f"{provider} has been assigned to help you. "
            f"ETA ~{eta} minutes." if eta else f"{provider} has been assigned to help you."
        ),
        "en_route": f"{provider} is en route to {addr}.",
        "arrived": f"{provider} has arrived at {addr}.",
        "completed": "Job complete. Thank you for using RoadSide.",
        "new_job_offer": (
            f"New job at {addr}. "
            f"Distance ~{data.get('distance_km', '?')} km. "
            "Reply YES to accept or NO to decline."
        ),
        "no_provider_alert": (
            f"ATTENTION: incident at {addr} has no available provider. Manual dispatch required."
        ),
        "custom": data.get("text", "Notification from RoadSide."),
    }
    return fallbacks.get(event, "Update from RoadSide.")

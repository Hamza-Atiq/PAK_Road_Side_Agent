"""Demo-scenario shared fixtures.

These scenarios exercise the full agent pipeline against a real DB with
external integrations stubbed:
- Anthropic Claude → MagicMock that returns canned JSON / text
- Twilio → captured into an in-memory list (asserts on sent messages)
- ORS routing → stubbed to deterministic ETAs

Goal: each scenario file reads top-to-bottom like a demo script for judges
and can be run independently with `pytest tests/demo/test_<n>_<name>.py -s`.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest
import pytest_asyncio


# ============================================================
# Shared helpers re-exported into demo modules
# ============================================================


@dataclass
class SentMessage:
    to_phone: str
    channel: str
    content: str


@dataclass
class StubBus:
    """Captures everything Twilio + the websocket broadcaster would have sent."""

    sent_messages: list[SentMessage] = field(default_factory=list)
    broadcasts: list[dict[str, Any]] = field(default_factory=list)


@pytest_asyncio.fixture
async def bus(monkeypatch) -> StubBus:
    """Wire up Twilio + WS broadcast stubs and yield the capture buffer."""
    captured = StubBus()

    # ---- Twilio ----
    async def _fake_send_sms(*, to: str, body: str, **_kw):
        captured.sent_messages.append(SentMessage(to_phone=to, channel="sms", content=body))
        from app.services.twilio_service import TwilioSendResult
        return TwilioSendResult(twilio_sid=f"SM_fake_{len(captured.sent_messages):04d}",
                                status="queued", channel="sms")

    async def _fake_send_whatsapp(*, to: str, body: str, **_kw):
        captured.sent_messages.append(
            SentMessage(to_phone=to, channel="whatsapp", content=body)
        )
        from app.services.twilio_service import TwilioSendResult
        return TwilioSendResult(twilio_sid=f"WA_fake_{len(captured.sent_messages):04d}",
                                status="queued", channel="whatsapp")

    # NB: `app.tools.twilio_tool` and `app.api.webhooks` import these by name
    # at module-load time, so we MUST patch every site that holds a reference.
    from app.services import twilio_service
    monkeypatch.setattr(twilio_service, "send_sms", _fake_send_sms)
    monkeypatch.setattr(twilio_service, "send_whatsapp", _fake_send_whatsapp)
    from app.tools import twilio_tool as _twilio_tool
    monkeypatch.setattr(_twilio_tool, "send_sms", _fake_send_sms)
    monkeypatch.setattr(_twilio_tool, "send_whatsapp", _fake_send_whatsapp)
    from app.api import webhooks as _webhooks
    monkeypatch.setattr(_webhooks, "send_whatsapp", _fake_send_whatsapp)

    # ---- WebSocket broadcast ----
    async def _fake_broadcast(**kwargs):
        captured.broadcasts.append(kwargs)

    from app.tools import notification_tool
    monkeypatch.setattr(notification_tool, "broadcast_incident_event", _fake_broadcast)
    # Some modules import broadcast_incident_event directly
    import app.api.incidents as inc_api
    monkeypatch.setattr(inc_api, "broadcast_incident_event", _fake_broadcast)
    import app.agents.orchestrator as orch_mod
    monkeypatch.setattr(orch_mod, "broadcast_incident_event", _fake_broadcast)

    yield captured


def fake_anthropic_response(text: str) -> MagicMock:
    """Build a MagicMock that mimics anthropic AsyncClient.messages.create."""
    block = MagicMock()
    block.type = "text"
    block.text = text
    response = MagicMock()
    response.content = [block]
    client = MagicMock()
    client.messages = MagicMock()
    client.messages.create = AsyncMock(return_value=response)
    return client


def fake_anthropic_router(routes: dict[str, str]) -> MagicMock:
    """Build a MagicMock that returns different texts depending on the SYSTEM
    prompt of the call. Useful when one scenario invokes multiple agents.

    routes: keyword-in-system-prompt → text to return.
    """
    async def _create(**kw):
        system = kw.get("system", "") or ""
        for key, body in routes.items():
            if key in system:
                block = MagicMock(); block.type = "text"; block.text = body
                response = MagicMock(); response.content = [block]
                return response
        # fallback
        block = MagicMock(); block.type = "text"; block.text = "{}"
        response = MagicMock(); response.content = [block]
        return response
    client = MagicMock()
    client.messages = MagicMock()
    client.messages.create = AsyncMock(side_effect=_create)
    return client


# ============================================================
# DB seed helpers — small, focused, demo-only
# ============================================================


async def seed_customer(db_session, *, phone: str, name: str = "Demo Customer"):
    from app.models.user import User
    from app.models.enums import UserRole
    from app.services.security import hash_password
    user = User(
        phone=phone, name=name, role=UserRole.customer.value,
        password_hash=hash_password("password123"),
        is_active=True, is_phone_verified=True,
    )
    db_session.add(user)
    await db_session.flush()
    return user


async def seed_admin(db_session, *, phone: str = "+15550000099"):
    from app.models.user import User
    from app.models.enums import UserRole
    from app.services.security import hash_password
    user = User(
        phone=phone, name="Demo Admin", role=UserRole.admin.value,
        password_hash=hash_password("admin123"),
        is_active=True, is_phone_verified=True,
    )
    db_session.add(user)
    await db_session.flush()
    return user


async def seed_provider(
    db_session, *, phone: str, name: str,
    lat: float = 37.7749, lng: float = -122.4194,
    service_type: str = "mechanic",
    is_available: bool = True,
):
    from app.models.user import User
    from app.models.provider import Provider
    from app.models.enums import UserRole
    from app.services.security import hash_password
    user = User(
        phone=phone, name=name, role=UserRole.provider.value,
        password_hash=hash_password("provider123"),
        is_active=True, is_phone_verified=True,
    )
    db_session.add(user)
    await db_session.flush()
    prov = Provider(
        id=user.id, service_type=service_type,
        is_available=is_available, is_approved=True,
        location=f"SRID=4326;POINT({lng} {lat})",
    )
    db_session.add(prov)
    await db_session.flush()
    return user, prov


async def seed_incident(
    db_session, *, customer_id, description: str = "engine won't start",
    image_url: str | None = None, voice_url: str | None = None,
    lat: float = 37.7749, lng: float = -122.4194,
):
    from app.models.incident import Incident
    from app.models.enums import IncidentStatus
    inc = Incident(
        customer_id=customer_id,
        lat=lat, lng=lng,
        description=description,
        image_url=image_url, voice_url=voice_url,
        status=IncidentStatus.REPORTED.value,
    )
    db_session.add(inc)
    await db_session.flush()
    return inc

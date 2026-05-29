"""Tests for twilio_service dev fallback, notification broker, CommunicationAgent."""
from __future__ import annotations

import asyncio
import json
import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.agents.base import AgentContext
from app.agents.communication import (
    EVENT_KEYS,
    CommunicationAgent,
    _fallback_message,
)
from app.models.enums import DeliveryStatus, MessageType
from app.services.security import hash_password
from app.services.twilio_service import (
    TwilioSendError,
    send_sms,
    send_whatsapp,
    validate_signature,
)
from app.tools.notification_tool import (
    broadcast_admin_event,
    broadcast_incident_event,
    reset_registry_for_tests,
    subscribe_admin,
    subscribe_incident,
    subscriber_counts,
)
from app.tools.twilio_tool import twilio_status_to_delivery


# ============================================================
# Section 1 — Twilio dev fallback (pure)
# ============================================================


@pytest.mark.asyncio
async def test_send_sms_dev_returns_fake_sid():
    result = await send_sms(to="+15551234567", body="test")
    assert result.twilio_sid.startswith("dev-sid-")
    assert result.status == "dev_skipped"
    assert result.channel == "sms"


@pytest.mark.asyncio
async def test_send_whatsapp_dev_returns_fake_sid():
    result = await send_whatsapp(to="+15551234567", body="test")
    assert result.twilio_sid.startswith("dev-sid-")
    assert result.channel == "whatsapp"


@pytest.mark.asyncio
async def test_send_empty_body_raises():
    with pytest.raises(TwilioSendError):
        await send_sms(to="+15551234567", body="")
    with pytest.raises(TwilioSendError):
        await send_sms(to="", body="hi")


def test_validate_signature_dev_mode_returns_true():
    """In dev fallback (no creds), validation is skipped to allow local testing."""
    assert validate_signature(url="http://x/y", params={"a": "b"}, signature=None) is True


# ============================================================
# Section 2 — Twilio status-to-delivery mapping (pure)
# ============================================================


@pytest.mark.parametrize("twilio_status,expected", [
    ("queued", DeliveryStatus.SENT),
    ("sending", DeliveryStatus.SENT),
    ("sent", DeliveryStatus.SENT),
    ("delivered", DeliveryStatus.DELIVERED),
    ("read", DeliveryStatus.DELIVERED),
    ("failed", DeliveryStatus.FAILED),
    ("undelivered", DeliveryStatus.FAILED),
    ("canceled", DeliveryStatus.FAILED),
    ("dev_skipped", DeliveryStatus.SENT),
    ("totally_unknown", DeliveryStatus.PENDING),
])
def test_status_mapping(twilio_status, expected):
    assert twilio_status_to_delivery(twilio_status) == expected


# ============================================================
# Section 3 — Notification broker (pure, no DB)
# ============================================================


@pytest.mark.asyncio
async def test_subscribe_and_broadcast_incident():
    reset_registry_for_tests()
    incident_id = uuid.uuid4()
    received: list = []

    async def cb(payload):
        received.append(payload)

    unsub = subscribe_incident(incident_id, cb)
    await broadcast_incident_event(
        incident_id=incident_id, event="STATUS_CHANGED", data={"status": "ASSIGNED"}
    )
    assert len(received) == 1
    assert received[0]["event"] == "STATUS_CHANGED"
    assert received[0]["incident_id"] == str(incident_id)
    unsub()


@pytest.mark.asyncio
async def test_admin_subscribers_get_all_incident_events():
    reset_registry_for_tests()
    incident_id = uuid.uuid4()
    admin_events: list = []

    async def admin_cb(payload):
        admin_events.append(payload)

    unsub = subscribe_admin(admin_cb)
    await broadcast_incident_event(
        incident_id=incident_id, event="STATUS_CHANGED", data={},
    )
    await broadcast_admin_event(event="PROVIDER_LOCATION", data={"lat": 1.0, "lng": 2.0})
    assert len(admin_events) == 2
    unsub()


@pytest.mark.asyncio
async def test_failing_subscriber_does_not_break_others():
    reset_registry_for_tests()
    incident_id = uuid.uuid4()
    good_received = []

    async def bad_cb(_):
        raise RuntimeError("intentionally broken")

    async def good_cb(p):
        good_received.append(p)

    subscribe_incident(incident_id, bad_cb)
    subscribe_incident(incident_id, good_cb)
    await broadcast_incident_event(
        incident_id=incident_id, event="STATUS_CHANGED", data={}
    )
    assert len(good_received) == 1


@pytest.mark.asyncio
async def test_unsubscribe_stops_delivery():
    reset_registry_for_tests()
    incident_id = uuid.uuid4()
    received = []

    async def cb(p):
        received.append(p)

    unsub = subscribe_incident(incident_id, cb)
    await broadcast_incident_event(incident_id=incident_id, event="STATUS_CHANGED")
    unsub()
    await broadcast_incident_event(incident_id=incident_id, event="STATUS_CHANGED")
    assert len(received) == 1


def test_subscriber_counts_introspection():
    reset_registry_for_tests()
    assert subscriber_counts() == {
        "incident_streams": 0,
        "admin_subscribers": 0,
        "incident_subscriber_total": 0,
    }


# ============================================================
# Section 4 — CommunicationAgent fallback messages (pure)
# ============================================================


def test_fallback_messages_for_every_event():
    """The fallback templates must cover every public event."""
    data = {
        "provider_name": "Tom", "eta_minutes": 8, "address": "Main St",
        "distance_km": 3.2, "text": "custom test",
    }
    for event in EVENT_KEYS:
        msg = _fallback_message(event, data)
        assert msg and isinstance(msg, str)
        assert len(msg) < 320, f"fallback for {event} too long: {len(msg)}"


def test_provider_assigned_fallback_includes_eta():
    msg = _fallback_message("provider_assigned", {
        "provider_name": "Tom", "eta_minutes": 8,
    })
    assert "Tom" in msg
    assert "8" in msg


def test_new_job_offer_includes_reply_instructions():
    msg = _fallback_message("new_job_offer", {
        "address": "Market & 4th", "distance_km": 2.5,
    })
    assert "YES" in msg.upper()
    assert "NO" in msg.upper()


# ============================================================
# Section 5 — CommunicationAgent end-to-end (mocked Claude, real DB)
# ============================================================


def _mock_claude_returning(text: str) -> MagicMock:
    block = MagicMock()
    block.type = "text"
    block.text = text
    response = MagicMock()
    response.content = [block]
    client = MagicMock()
    client.messages = MagicMock()
    client.messages.create = AsyncMock(return_value=response)
    return client


async def _make_customer_user(db_session, phone="+15557770001"):
    from app.models.user import User
    user = User(
        phone=phone, name="Customer", role="customer",
        password_hash=hash_password("password123"),
        is_active=True, is_phone_verified=True,
    )
    db_session.add(user)
    await db_session.flush()
    return user


async def _make_incident(db_session, customer_id):
    from app.models.incident import Incident
    incident = Incident(
        customer_id=customer_id, lat=37.7749, lng=-122.4194,
        description="test", status="ASSIGNED",
    )
    db_session.add(incident)
    await db_session.flush()
    return incident


@pytest.mark.asyncio
async def test_communication_agent_sends_generated_message(db_session):
    customer = await _make_customer_user(db_session, "+15557770010")
    incident = await _make_incident(db_session, customer.id)

    client = _mock_claude_returning(
        "Tom is on the way. ETA about 8 minutes. He'll call when nearby."
    )
    agent = CommunicationAgent(anthropic_client=client)
    ctx = AgentContext(
        db=db_session, incident_id=incident.id,
        payload={
            "event": "en_route",
            "to_phone": customer.phone,
            "context_data": {"provider_name": "Tom", "eta_minutes": 8},
        },
    )
    result = await agent.run(ctx)
    assert result.success
    assert result.output.sent is True
    assert "Tom" in result.output.content
    # Message row persisted
    from sqlalchemy import select
    from app.models.message import Message
    msgs = (await db_session.execute(
        select(Message).where(Message.incident_id == incident.id)
    )).scalars().all()
    assert len(msgs) == 1
    assert msgs[0].sender_agent == "CommunicationAgent"
    assert msgs[0].msg_type == MessageType.SMS.value


@pytest.mark.asyncio
async def test_communication_agent_uses_content_override(db_session):
    """If caller supplies content_override, Claude is NOT called."""
    customer = await _make_customer_user(db_session, "+15557770011")
    incident = await _make_incident(db_session, customer.id)

    client = MagicMock()
    client.messages = MagicMock()
    client.messages.create = AsyncMock(
        side_effect=AssertionError("Claude must not be called when content_override is set")
    )

    agent = CommunicationAgent(anthropic_client=client)
    ctx = AgentContext(
        db=db_session, incident_id=incident.id,
        payload={
            "event": "custom",
            "to_phone": customer.phone,
            "content_override": "Manual admin message",
            "context_data": {},
        },
    )
    result = await agent.run(ctx)
    assert result.success
    assert result.output.content == "Manual admin message"


@pytest.mark.asyncio
async def test_communication_agent_unknown_event_rejected(db_session):
    customer = await _make_customer_user(db_session, "+15557770012")
    agent = CommunicationAgent(anthropic_client=MagicMock())
    ctx = AgentContext(
        db=db_session,
        payload={"event": "nonexistent", "to_phone": customer.phone, "context_data": {}},
    )
    result = await agent.run(ctx)
    assert result.success is False
    assert "unknown event" in result.error.lower()


@pytest.mark.asyncio
async def test_communication_agent_tool_authorization(db_session):
    """Strict allow-list: cannot call db_write or geo tools."""
    agent = CommunicationAgent(anthropic_client=MagicMock())
    assert "twilio_tool" in agent.tools
    assert "notification_tool" in agent.tools
    from app.agents.base import ToolNotAuthorizedError
    for forbidden in ("db_write_tool", "geo_tool", "routing_tool", "vision_tool"):
        with pytest.raises(ToolNotAuthorizedError):
            agent._check_tool_authorized(forbidden)


@pytest.mark.asyncio
async def test_claude_failure_falls_back_to_template(db_session):
    """Claude error → fallback template is used so the message still goes out."""
    customer = await _make_customer_user(db_session, "+15557770013")
    incident = await _make_incident(db_session, customer.id)
    client = MagicMock()
    client.messages = MagicMock()
    client.messages.create = AsyncMock(side_effect=RuntimeError("network down"))

    agent = CommunicationAgent(anthropic_client=client)
    ctx = AgentContext(
        db=db_session, incident_id=incident.id,
        payload={
            "event": "arrived",
            "to_phone": customer.phone,
            "context_data": {"provider_name": "Sarah", "address": "5th Ave"},
        },
    )
    result = await agent.run(ctx)
    assert result.success
    assert result.output.sent is True
    assert "Sarah" in result.output.content
    assert "5th Ave" in result.output.content

"""Tests for Twilio status-callback webhooks."""
from __future__ import annotations

import uuid

import pytest

from app.models.enums import DeliveryStatus, MessageType
from app.models.message import Message


async def _make_message(db_session, *, sid="SM_test_sid_001", channel=MessageType.SMS):
    msg = Message(
        msg_type=channel.value,
        content="Hello from the test",
        recipient_phone="+15551234567",
        twilio_sid=sid,
        delivery_status=DeliveryStatus.SENT.value,
    )
    db_session.add(msg)
    await db_session.flush()
    return msg


@pytest.mark.asyncio
async def test_sms_status_delivered_updates_row(client, db_session):
    msg = await _make_message(db_session, sid="SM_delivered_001")
    # Dev mode skips signature validation; no header needed
    response = await client.post(
        "/api/webhooks/twilio/sms-status",
        data={
            "MessageSid": "SM_delivered_001",
            "MessageStatus": "delivered",
            "To": "+15551234567",
        },
    )
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["delivery_status"] == DeliveryStatus.DELIVERED.value
    await db_session.refresh(msg)
    assert msg.delivery_status == DeliveryStatus.DELIVERED.value
    assert msg.delivered_at is not None


@pytest.mark.asyncio
async def test_sms_status_failed_triggers_whatsapp_fallback(client, db_session):
    """When an SMS fails, a WhatsApp message must be sent with the same content."""
    msg = await _make_message(db_session, sid="SM_failed_001")
    response = await client.post(
        "/api/webhooks/twilio/sms-status",
        data={
            "MessageSid": "SM_failed_001",
            "MessageStatus": "failed",
            "ErrorCode": "30003",
            "To": "+15551234567",
        },
    )
    assert response.status_code == 200
    body = response.json()
    assert body["fallback_triggered"] == "true"
    # A second Message row of type WHATSAPP must exist with the same content
    from sqlalchemy import select
    rows = (await db_session.execute(
        select(Message).where(Message.recipient_phone == "+15551234567")
    )).scalars().all()
    types = {r.msg_type for r in rows}
    assert MessageType.SMS.value in types
    assert MessageType.WHATSAPP.value in types
    wa = next(r for r in rows if r.msg_type == MessageType.WHATSAPP.value)
    assert wa.content == "Hello from the test"


@pytest.mark.asyncio
async def test_whatsapp_status_failed_does_not_loop(client, db_session):
    """A failed WhatsApp must NOT trigger another fallback (no loop)."""
    msg = await _make_message(db_session, sid="WA_failed_001", channel=MessageType.WHATSAPP)
    response = await client.post(
        "/api/webhooks/twilio/whatsapp-status",
        data={
            "MessageSid": "WA_failed_001",
            "MessageStatus": "failed",
            "To": "+15551234567",
        },
    )
    assert response.status_code == 200
    body = response.json()
    assert body["fallback_triggered"] == "false"


@pytest.mark.asyncio
async def test_unknown_sid_returns_ok_to_stop_retries(client, db_session):
    """Unknown SIDs return 200 (not 4xx) so Twilio stops retrying."""
    response = await client.post(
        "/api/webhooks/twilio/sms-status",
        data={
            "MessageSid": "SM_never_seen",
            "MessageStatus": "delivered",
            "To": "+15551234567",
        },
    )
    assert response.status_code == 200
    assert response.json()["status"] == "unknown_sid"


@pytest.mark.asyncio
async def test_missing_required_fields_rejected(client):
    response = await client.post(
        "/api/webhooks/twilio/sms-status",
        data={"MessageSid": "SM_x"},  # missing MessageStatus
    )
    assert response.status_code == 400

"""Agent-facing Twilio tool: send + persist message row.

Wraps `twilio_service` and writes a `Message` row in the same call, so the
caller never forgets to log what was sent. The Message row stores `twilio_sid`
which the webhook handler uses to find the row when delivery status arrives.
"""
from __future__ import annotations

import uuid
from typing import Literal

from sqlalchemy.ext.asyncio import AsyncSession

from app.middleware.logging import get_logger
from app.models.enums import DeliveryStatus, MessageType
from app.models.message import Message
from app.services.twilio_service import (
    TwilioSendError,
    TwilioSendResult,
    send_sms,
    send_whatsapp,
)

log = get_logger("tools.twilio")

Channel = Literal["sms", "whatsapp"]


# Mapping from Twilio's lifecycle states to our compact DeliveryStatus enum.
_TWILIO_TO_DELIVERY = {
    "queued": DeliveryStatus.SENT,
    "sending": DeliveryStatus.SENT,
    "sent": DeliveryStatus.SENT,
    "delivered": DeliveryStatus.DELIVERED,
    "read": DeliveryStatus.DELIVERED,
    "failed": DeliveryStatus.FAILED,
    "undelivered": DeliveryStatus.FAILED,
    "canceled": DeliveryStatus.FAILED,
    "dev_skipped": DeliveryStatus.SENT,  # treat dev as sent for downstream logic
}


def twilio_status_to_delivery(status: str) -> DeliveryStatus:
    return _TWILIO_TO_DELIVERY.get(status.lower(), DeliveryStatus.PENDING)


async def send_message(
    db: AsyncSession,
    *,
    to_phone: str,
    body: str,
    channel: Channel = "sms",
    incident_id: uuid.UUID | None = None,
    sender_agent: str | None = None,
) -> Message:
    """Send a message and persist the row. Returns the Message instance."""
    if not to_phone:
        raise TwilioSendError("to_phone is required")
    if not body:
        raise TwilioSendError("body is required")

    msg_type = MessageType.SMS if channel == "sms" else MessageType.WHATSAPP

    # Pre-create the row in PENDING state so any failure is still auditable
    row = Message(
        incident_id=incident_id,
        sender_agent=sender_agent,
        msg_type=msg_type.value,
        content=body,
        recipient_phone=to_phone,
        delivery_status=DeliveryStatus.PENDING.value,
    )
    db.add(row)
    await db.flush()

    try:
        result: TwilioSendResult = (
            await send_sms(to=to_phone, body=body)
            if channel == "sms"
            else await send_whatsapp(to=to_phone, body=body)
        )
    except TwilioSendError as exc:
        row.delivery_status = DeliveryStatus.FAILED.value
        row.error_message = str(exc)
        await db.flush()
        log.warning("twilio_send_failed", channel=channel, to=to_phone, error=str(exc))
        raise

    row.twilio_sid = result.twilio_sid
    row.delivery_status = twilio_status_to_delivery(result.status).value
    await db.flush()

    log.info(
        "twilio_message_sent",
        message_id=str(row.id),
        sid=result.twilio_sid,
        channel=channel,
        to=to_phone,
        agent=sender_agent,
    )
    return row

"""Twilio status-callback webhooks.

Twilio hits these endpoints when a message's delivery state changes. We:
1. Verify the request signature so attackers can't forge delivery reports.
2. Find the `Message` row by `twilio_sid` and update `delivery_status`.
3. On a hard `failed` / `undelivered` event for SMS, fire a WhatsApp fallback
   to the same recipient — this is the resilience promise from SPEC §3.5.
"""
from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Header, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.metrics import sms_failures_total
from app.middleware.logging import get_logger
from app.models.enums import DeliveryStatus, MessageType
from app.models.message import Message
from app.services.twilio_service import (
    TwilioSendError,
    send_whatsapp,
    validate_signature,
)
from app.tools.twilio_tool import twilio_status_to_delivery

log = get_logger("api.webhooks")

router = APIRouter(prefix="/api/webhooks/twilio", tags=["webhooks"])


# ----------------------------------------------------------------------
# Helpers
# ----------------------------------------------------------------------


def _full_url(request: Request) -> str:
    """Reconstruct the public URL Twilio used, for signature validation.

    Honors X-Forwarded-Proto / X-Forwarded-Host if present so this works
    behind Nginx in production. Otherwise, falls back to the local scope.
    """
    scheme = request.headers.get("x-forwarded-proto") or request.url.scheme
    host = request.headers.get("x-forwarded-host") or request.url.netloc
    return f"{scheme}://{host}{request.url.path}"


async def _read_form(request: Request) -> dict[str, str]:
    raw = await request.form()
    return {k: str(v) for k, v in raw.items()}


async def _process_status_callback(
    request: Request,
    db: AsyncSession,
    x_twilio_signature: str | None,
    expected_channel: MessageType,
) -> dict[str, str]:
    """Common handler for both SMS and WhatsApp status callbacks."""
    params = await _read_form(request)
    url = _full_url(request)

    if not validate_signature(url=url, params=params, signature=x_twilio_signature):
        log.warning(
            "twilio_webhook_signature_invalid",
            sid=params.get("MessageSid"),
            url=url,
        )
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="invalid signature")

    sid = params.get("MessageSid")
    new_status = (params.get("MessageStatus") or "").lower()
    error_code = params.get("ErrorCode")
    to_phone = params.get("To")

    if not sid or not new_status:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="missing MessageSid or MessageStatus",
        )

    message = await db.scalar(select(Message).where(Message.twilio_sid == sid))
    if message is None:
        # Unknown SID — return 200 so Twilio stops retrying, but log it.
        log.warning("twilio_webhook_unknown_sid", sid=sid)
        return {"status": "unknown_sid"}

    mapped = twilio_status_to_delivery(new_status)
    message.delivery_status = mapped.value
    if mapped == DeliveryStatus.FAILED:
        message.error_message = f"twilio_status={new_status}, error_code={error_code}"
        # Record the late-arriving failure (the initial send was already counted as sent)
        sms_failures_total.labels(channel=expected_channel.value.lower()).inc()
    if mapped == DeliveryStatus.DELIVERED:
        from datetime import UTC, datetime
        message.delivered_at = datetime.now(UTC)
    await db.flush()

    # ---- WhatsApp fallback on SMS hard failures ----
    fallback_triggered = False
    if (
        expected_channel == MessageType.SMS
        and mapped == DeliveryStatus.FAILED
        and to_phone
        and message.content
    ):
        try:
            result = await send_whatsapp(to=to_phone, body=message.content)
            fallback_row = Message(
                incident_id=message.incident_id,
                sender_agent=message.sender_agent,
                msg_type=MessageType.WHATSAPP.value,
                content=message.content,
                recipient_phone=to_phone,
                twilio_sid=result.twilio_sid,
                delivery_status=twilio_status_to_delivery(result.status).value,
            )
            db.add(fallback_row)
            await db.flush()
            fallback_triggered = True
            log.info(
                "whatsapp_fallback_sent",
                original_sid=sid,
                fallback_sid=result.twilio_sid,
                to=to_phone,
            )
        except TwilioSendError as exc:
            log.warning("whatsapp_fallback_failed", original_sid=sid, error=str(exc))

    return {
        "status": "ok",
        "message_id": str(message.id),
        "delivery_status": message.delivery_status,
        "fallback_triggered": str(fallback_triggered).lower(),
    }


# ----------------------------------------------------------------------
# Routes
# ----------------------------------------------------------------------


@router.post("/sms-status", summary="Twilio SMS delivery callback")
async def sms_status(
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    x_twilio_signature: Annotated[str | None, Header(alias="X-Twilio-Signature")] = None,
) -> dict[str, str]:
    return await _process_status_callback(
        request, db, x_twilio_signature, MessageType.SMS
    )


@router.post("/whatsapp-status", summary="Twilio WhatsApp delivery callback")
async def whatsapp_status(
    request: Request,
    db: Annotated[AsyncSession, Depends(get_db)],
    x_twilio_signature: Annotated[str | None, Header(alias="X-Twilio-Signature")] = None,
) -> dict[str, str]:
    return await _process_status_callback(
        request, db, x_twilio_signature, MessageType.WHATSAPP
    )

"""Low-level Twilio API wrapper.

Provides async-compatible `send_sms`, `send_whatsapp`, and webhook signature
validation. The Twilio SDK is synchronous, so we run blocking calls in a
worker thread via `asyncio.to_thread` to keep the FastAPI event loop free.

Dev fallback
------------
If `TWILIO_ACCOUNT_SID` is empty AND `APP_ENV != production`, sends are
no-ops that return a fake `dev-sid-...` so the rest of the flow (DB log,
agent reasoning) works without a real Twilio account. Production with no
credentials raises `TwilioNotConfiguredError`.
"""
from __future__ import annotations

import asyncio
import uuid
from dataclasses import dataclass
from typing import Literal

from twilio.base.exceptions import TwilioRestException
from twilio.request_validator import RequestValidator
from twilio.rest import Client

from app.config import settings
from app.metrics import record_sms
from app.middleware.logging import get_logger

log = get_logger("services.twilio")

Channel = Literal["sms", "whatsapp"]


# ----------------------------------------------------------------------
# Errors
# ----------------------------------------------------------------------


class TwilioNotConfiguredError(Exception):
    """Production attempted Twilio call without credentials."""


class TwilioSendError(Exception):
    """Twilio rejected the message (auth, format, recipient unreachable)."""


# ----------------------------------------------------------------------
# Result
# ----------------------------------------------------------------------


@dataclass
class TwilioSendResult:
    twilio_sid: str
    status: str  # initial Twilio status: 'queued' | 'sending' | 'dev_skipped'
    channel: Channel


# ----------------------------------------------------------------------
# Helpers
# ----------------------------------------------------------------------


def _is_dev_fallback() -> bool:
    return (
        not settings.TWILIO_ACCOUNT_SID
        and settings.APP_ENV != "production"
    )


def _twilio_client() -> Client:
    if not settings.TWILIO_ACCOUNT_SID or not settings.TWILIO_AUTH_TOKEN:
        raise TwilioNotConfiguredError("TWILIO_ACCOUNT_SID / TWILIO_AUTH_TOKEN missing")
    return Client(settings.TWILIO_ACCOUNT_SID, settings.TWILIO_AUTH_TOKEN)


def _status_callback_url(channel: Channel) -> str | None:
    base = (settings.TWILIO_CALLBACK_BASE_URL or settings.APP_BASE_URL).rstrip("/")
    if not base or base.startswith("http://localhost"):
        # Twilio cannot reach localhost; skip callback in dev unless explicitly tunnel'd
        return None
    return f"{base}/api/webhooks/twilio/{channel}-status"


def _dev_fake_sid() -> str:
    return f"dev-sid-{uuid.uuid4().hex[:16]}"


# ----------------------------------------------------------------------
# Sync senders (wrapped by async helpers below)
# ----------------------------------------------------------------------


def _sync_send_sms(*, to: str, body: str) -> TwilioSendResult:
    client = _twilio_client()
    cb = _status_callback_url("sms")
    try:
        msg = client.messages.create(
            from_=settings.TWILIO_FROM_NUMBER,
            to=to,
            body=body,
            status_callback=cb,
        )
    except TwilioRestException as exc:
        raise TwilioSendError(f"Twilio SMS send failed: {exc.msg}") from exc
    return TwilioSendResult(twilio_sid=msg.sid, status=msg.status or "queued", channel="sms")


def _sync_send_whatsapp(*, to: str, body: str) -> TwilioSendResult:
    client = _twilio_client()
    cb = _status_callback_url("whatsapp")
    to_addr = to if to.startswith("whatsapp:") else f"whatsapp:{to}"
    try:
        msg = client.messages.create(
            from_=settings.TWILIO_WHATSAPP_NUMBER,
            to=to_addr,
            body=body,
            status_callback=cb,
        )
    except TwilioRestException as exc:
        raise TwilioSendError(f"Twilio WhatsApp send failed: {exc.msg}") from exc
    return TwilioSendResult(twilio_sid=msg.sid, status=msg.status or "queued", channel="whatsapp")


# ----------------------------------------------------------------------
# Public async API
# ----------------------------------------------------------------------


async def send_sms(*, to: str, body: str) -> TwilioSendResult:
    """Send an SMS asynchronously. Returns Twilio SID and initial status."""
    if not to or not body:
        raise TwilioSendError("to and body are required")

    # Test-number bypass — same list used by OTP bypass; avoids trial-account 21608 errors.
    if to in settings.test_phone_numbers:
        sid = _dev_fake_sid()
        log.warning("twilio_test_number_skipped", channel="sms", to=to, sid=sid, preview=body[:80])
        record_sms("sms", success=True)
        return TwilioSendResult(twilio_sid=sid, status="test_skipped", channel="sms")

    if _is_dev_fallback():
        sid = _dev_fake_sid()
        log.warning("twilio_dev_skipped", channel="sms", to=to, sid=sid, preview=body[:80])
        record_sms("sms", success=True)
        return TwilioSendResult(twilio_sid=sid, status="dev_skipped", channel="sms")

    if not settings.TWILIO_FROM_NUMBER:
        raise TwilioNotConfiguredError("TWILIO_FROM_NUMBER is required in production")

    try:
        result = await asyncio.to_thread(_sync_send_sms, to=to, body=body)
    except TwilioSendError:
        record_sms("sms", success=False)
        raise
    record_sms("sms", success=True)
    return result


async def send_whatsapp(*, to: str, body: str) -> TwilioSendResult:
    """Send a WhatsApp message asynchronously."""
    if not to or not body:
        raise TwilioSendError("to and body are required")

    # Test-number bypass — avoids trial-account failures on unverified numbers.
    if to in settings.test_phone_numbers:
        sid = _dev_fake_sid()
        log.warning("twilio_test_number_skipped", channel="whatsapp", to=to, sid=sid, preview=body[:80])
        record_sms("whatsapp", success=True)
        return TwilioSendResult(twilio_sid=sid, status="test_skipped", channel="whatsapp")

    if _is_dev_fallback():
        sid = _dev_fake_sid()
        log.warning("twilio_dev_skipped", channel="whatsapp", to=to, sid=sid, preview=body[:80])
        record_sms("whatsapp", success=True)
        return TwilioSendResult(twilio_sid=sid, status="dev_skipped", channel="whatsapp")

    if not settings.TWILIO_WHATSAPP_NUMBER:
        raise TwilioNotConfiguredError("TWILIO_WHATSAPP_NUMBER is required in production")

    try:
        result = await asyncio.to_thread(_sync_send_whatsapp, to=to, body=body)
    except TwilioSendError:
        record_sms("whatsapp", success=False)
        raise
    record_sms("whatsapp", success=True)
    return result


# ----------------------------------------------------------------------
# Webhook signature validation
# ----------------------------------------------------------------------


def validate_signature(*, url: str, params: dict[str, str], signature: str | None) -> bool:
    """Verify that a webhook request is genuinely from Twilio.

    Always returns True in dev fallback mode (no auth token to validate with).
    Returns False if signature header is missing or fails verification.
    """
    if _is_dev_fallback():
        log.warning("twilio_signature_skipped_dev_mode")
        return True

    if not signature:
        return False
    if not settings.TWILIO_AUTH_TOKEN:
        # Production without auth token = misconfiguration; reject defensively.
        return False

    validator = RequestValidator(settings.TWILIO_AUTH_TOKEN)
    return validator.validate(url, params, signature)

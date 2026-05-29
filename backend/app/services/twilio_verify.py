"""Phone-number OTP via Twilio Verify.

Production: uses the Twilio Verify API.
Development: if TWILIO_VERIFY_SERVICE_SID is empty AND APP_ENV != production,
falls back to a fixed code (`DEV_OTP_CODE`) so the auth flow remains usable
without a live Twilio account. A WARN is logged each time so this can't ship
to production by accident.

The OTP service does not write to the database — verifying ownership of a
phone is enough; activating the user account is the auth API's responsibility.
"""
from __future__ import annotations

import logging
from typing import Literal

from twilio.base.exceptions import TwilioRestException
from twilio.rest import Client

from app.config import settings

log = logging.getLogger(__name__)

# Documented dev-only code. Never accepted in production.
DEV_OTP_CODE = "000000"

VerifyStatus = Literal["approved", "pending", "canceled", "expired", "failed"]


class OTPSendError(Exception):
    """Raised when Twilio cannot send the OTP."""


class OTPNotConfiguredError(Exception):
    """Raised when production attempts OTP without Twilio Verify credentials."""


def _twilio_client() -> Client:
    if not settings.TWILIO_ACCOUNT_SID or not settings.TWILIO_AUTH_TOKEN:
        raise OTPNotConfiguredError("Twilio credentials missing")
    return Client(settings.TWILIO_ACCOUNT_SID, settings.TWILIO_AUTH_TOKEN)


def _is_dev_fallback() -> bool:
    """True when we should accept the hardcoded dev OTP."""
    return (
        not settings.TWILIO_VERIFY_SERVICE_SID
        and settings.APP_ENV != "production"
    )


async def send_otp(phone: str, channel: Literal["sms", "whatsapp"] = "sms") -> None:
    """Trigger an OTP to the given E.164 phone number.

    In dev fallback mode this is a no-op (logs a warning instead).
    """
    if _is_dev_fallback():
        log.warning(
            "DEV MODE OTP — Twilio Verify not configured. "
            "Use code %s to verify %s",
            DEV_OTP_CODE,
            phone,
        )
        return

    if not settings.TWILIO_VERIFY_SERVICE_SID:
        raise OTPNotConfiguredError(
            "TWILIO_VERIFY_SERVICE_SID is required in production"
        )

    try:
        client = _twilio_client()
        client.verify.v2.services(
            settings.TWILIO_VERIFY_SERVICE_SID
        ).verifications.create(to=phone, channel=channel)
    except TwilioRestException as exc:
        raise OTPSendError(f"Twilio Verify send failed: {exc.msg}") from exc


async def check_otp(phone: str, code: str) -> bool:
    """Verify the OTP code submitted by the user. Returns True if approved."""
    if _is_dev_fallback():
        approved = code == DEV_OTP_CODE
        log.warning(
            "DEV MODE OTP check for %s: %s", phone, "approved" if approved else "rejected"
        )
        return approved

    if not settings.TWILIO_VERIFY_SERVICE_SID:
        raise OTPNotConfiguredError(
            "TWILIO_VERIFY_SERVICE_SID is required in production"
        )

    try:
        client = _twilio_client()
        check = client.verify.v2.services(
            settings.TWILIO_VERIFY_SERVICE_SID
        ).verification_checks.create(to=phone, code=code)
        return check.status == "approved"
    except TwilioRestException:
        return False

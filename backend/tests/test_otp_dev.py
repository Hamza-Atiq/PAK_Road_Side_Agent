"""Unit tests for the Twilio Verify dev-mode fallback."""
from __future__ import annotations

import os

import pytest

from app.services.twilio_verify import DEV_OTP_CODE, check_otp, send_otp


@pytest.mark.asyncio
async def test_dev_send_is_noop():
    """In dev mode with no Verify SID, send_otp must not raise."""
    # APP_ENV is 'development' and TWILIO_VERIFY_SERVICE_SID is empty in test env
    await send_otp("+15551234567")  # should just log a warning


@pytest.mark.asyncio
async def test_dev_check_accepts_fixed_code():
    assert await check_otp("+15551234567", DEV_OTP_CODE) is True


@pytest.mark.asyncio
async def test_dev_check_rejects_wrong_code():
    assert await check_otp("+15551234567", "999999") is False
    assert await check_otp("+15551234567", "") is False


@pytest.mark.asyncio
async def test_production_without_verify_sid_raises():
    """In production without Twilio config, calls must raise (fail closed)."""
    from app.services import twilio_verify

    # Temporarily patch settings via monkeypatching the module-level reference
    original_env = twilio_verify.settings.APP_ENV
    original_sid = twilio_verify.settings.TWILIO_VERIFY_SERVICE_SID
    try:
        twilio_verify.settings.APP_ENV = "production"
        twilio_verify.settings.TWILIO_VERIFY_SERVICE_SID = ""
        with pytest.raises(twilio_verify.OTPNotConfiguredError):
            await twilio_verify.send_otp("+15551234567")
        with pytest.raises(twilio_verify.OTPNotConfiguredError):
            await twilio_verify.check_otp("+15551234567", "000000")
    finally:
        twilio_verify.settings.APP_ENV = original_env
        twilio_verify.settings.TWILIO_VERIFY_SERVICE_SID = original_sid

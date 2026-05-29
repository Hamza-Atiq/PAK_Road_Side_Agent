"""Helpers for recording security events and enforcing the abuse policy.

The Guardrail (and any other security-aware code path) calls
`record_injection_attempt()` whenever something malicious or suspicious is
detected. This:
1. Encrypts the raw input (never stored plain).
2. Writes a `security_events` row for later review.
3. Increments the user's `abuse_count`.
4. Auto-suspends the user (sets `is_active = False`) once the configurable
   threshold is reached inside the rolling window.
"""
from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from typing import Iterable

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.middleware.logging import get_logger
from app.models.enums import SecurityEventType
from app.models.security_event import SecurityEvent
from app.models.user import User
from app.services.encryption import encrypt_str

log = get_logger("security_events")


async def record_injection_attempt(
    db: AsyncSession,
    *,
    user_id: uuid.UUID | None,
    raw_input: str,
    flagged_patterns: Iterable[str] | None = None,
    ip_address: str | None = None,
    user_agent: str | None = None,
    event_type: SecurityEventType = SecurityEventType.INJECTION_ATTEMPT,
) -> SecurityEvent:
    """Persist one security event row with the raw input encrypted at rest."""
    encrypted = encrypt_str(raw_input) if raw_input else None
    patterns_list = list(flagged_patterns) if flagged_patterns else None

    event = SecurityEvent(
        user_id=user_id,
        event_type=event_type.value,
        raw_input=encrypted,
        flagged_patterns=patterns_list,
        ip_address=ip_address,
        user_agent=user_agent,
    )
    db.add(event)
    await db.flush()

    log.warning(
        "security_event_recorded",
        event_type=event_type.value,
        user_id=str(user_id) if user_id else None,
        patterns=patterns_list,
    )
    return event


async def bump_abuse_and_maybe_suspend(
    db: AsyncSession, *, user_id: uuid.UUID
) -> tuple[int, bool]:
    """Increment users.abuse_count for the given user; auto-suspend if threshold reached
    in the configured window.

    Returns: (new_abuse_count, suspended_now)
    """
    user = await db.get(User, user_id)
    if user is None:
        # Shouldn't happen, but handle gracefully (e.g., user deleted mid-flow)
        return (0, False)

    user.abuse_count = (user.abuse_count or 0) + 1
    new_count = user.abuse_count

    # Count recent events for this user inside the rolling window
    window_start = datetime.now(UTC) - timedelta(hours=settings.ABUSE_WINDOW_HOURS)
    recent_count: int = await db.scalar(  # type: ignore[assignment]
        select(func.count())
        .select_from(SecurityEvent)
        .where(SecurityEvent.user_id == user_id)
        .where(SecurityEvent.created_at >= window_start)
    ) or 0

    suspended_now = False
    if (
        recent_count >= settings.ABUSE_SUSPEND_THRESHOLD
        and user.is_active
    ):
        user.is_active = False
        suspended_now = True
        await record_injection_attempt(
            db,
            user_id=user_id,
            raw_input=f"auto-suspended after {recent_count} events in {settings.ABUSE_WINDOW_HOURS}h",
            event_type=SecurityEventType.SUSPENDED,
        )
        log.warning(
            "user_auto_suspended",
            user_id=str(user_id),
            recent_count=recent_count,
            window_hours=settings.ABUSE_WINDOW_HOURS,
        )

    await db.flush()
    return (new_count, suspended_now)

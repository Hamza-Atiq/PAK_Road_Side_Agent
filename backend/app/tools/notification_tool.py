"""In-memory event broker for real-time UI updates.

Agents call `broadcast_incident_event()` whenever something changes.
Subscribers (typically WebSocket connections registered in Phase 8) receive
the event through a callback they pre-registered.

This is intentionally process-local. A single API replica is fine for MVP.
For horizontal scaling, swap the registry for a Redis pub/sub backend —
the public interface (`broadcast_*`, `subscribe_*`) stays unchanged.
"""
from __future__ import annotations

import asyncio
import uuid
from collections import defaultdict
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any, Literal

from app.middleware.logging import get_logger

log = get_logger("tools.notification")

EventType = Literal[
    "STATUS_CHANGED",
    "PROVIDER_LOCATION",
    "NO_PROVIDER_ALERT",
    "MESSAGE_SENT",
    "INCIDENT_CREATED",
    "AGENT_STEP",
]

Subscriber = Callable[[dict[str, Any]], Awaitable[None]]


@dataclass
class _Registry:
    incident_subs: dict[uuid.UUID, list[Subscriber]] = field(default_factory=lambda: defaultdict(list))
    admin_subs: list[Subscriber] = field(default_factory=list)


_registry = _Registry()


# ----------------------------------------------------------------------
# Subscription API (used by WS endpoints in Phase 8)
# ----------------------------------------------------------------------


def subscribe_incident(incident_id: uuid.UUID, callback: Subscriber) -> Callable[[], None]:
    """Register a callback for events about one incident. Returns an unsubscribe fn."""
    _registry.incident_subs[incident_id].append(callback)

    def _unsub() -> None:
        try:
            _registry.incident_subs[incident_id].remove(callback)
        except ValueError:
            pass

    return _unsub


def subscribe_admin(callback: Subscriber) -> Callable[[], None]:
    """Register a callback for the admin firehose (all events)."""
    _registry.admin_subs.append(callback)

    def _unsub() -> None:
        try:
            _registry.admin_subs.remove(callback)
        except ValueError:
            pass

    return _unsub


# ----------------------------------------------------------------------
# Publish API (used by agents and API routes)
# ----------------------------------------------------------------------


def _now_iso() -> str:
    return datetime.now(UTC).isoformat()


async def _fanout(payload: dict[str, Any], subs: list[Subscriber]) -> None:
    if not subs:
        return
    # Run all subscriber callbacks concurrently; isolate failures so one bad
    # subscriber doesn't break the rest.
    results = await asyncio.gather(
        *(_safe_call(sub, payload) for sub in list(subs)),
        return_exceptions=True,
    )
    for r in results:
        if isinstance(r, Exception):
            log.warning("notification_subscriber_error", error=str(r))


async def _safe_call(sub: Subscriber, payload: dict[str, Any]) -> None:
    try:
        await sub(payload)
    except Exception as exc:  # noqa: BLE001
        log.warning("subscriber_callback_failed", error=str(exc))


async def broadcast_incident_event(
    *,
    incident_id: uuid.UUID,
    event: EventType,
    data: dict[str, Any] | None = None,
    agent: str | None = None,
) -> None:
    """Send an event to subscribers of `incident_id` and to the admin firehose."""
    payload = {
        "event": event,
        "incident_id": str(incident_id),
        "agent": agent,
        "timestamp": _now_iso(),
        "data": data or {},
    }
    log.info("broadcast_incident", event_type=event, incident_id=str(incident_id), agent=agent)

    incident_subs = _registry.incident_subs.get(incident_id, [])
    admin_subs = _registry.admin_subs
    await asyncio.gather(
        _fanout(payload, incident_subs),
        _fanout(payload, admin_subs),
    )


async def broadcast_admin_event(
    *,
    event: EventType,
    data: dict[str, Any] | None = None,
    agent: str | None = None,
) -> None:
    """Send an admin-only event (e.g. provider location ping, NO_PROVIDER alert)."""
    payload = {
        "event": event,
        "incident_id": None,
        "agent": agent,
        "timestamp": _now_iso(),
        "data": data or {},
    }
    log.info("broadcast_admin", event_type=event, agent=agent)
    await _fanout(payload, _registry.admin_subs)


# ----------------------------------------------------------------------
# Test / introspection helpers
# ----------------------------------------------------------------------


def reset_registry_for_tests() -> None:
    """Clear all subscriptions. Use only from test setup/teardown."""
    _registry.incident_subs.clear()
    _registry.admin_subs.clear()


def subscriber_counts() -> dict[str, int]:
    return {
        "incident_streams": len(_registry.incident_subs),
        "admin_subscribers": len(_registry.admin_subs),
        "incident_subscriber_total": sum(len(v) for v in _registry.incident_subs.values()),
    }

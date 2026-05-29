"""WebSocket endpoints — real-time push to customer / provider / admin panels.

Auth: WebSocket browsers can't send custom headers easily, so JWT goes in a
query param `?token=<access_token>`. We decode + validate the same way the
HTTP middleware does, then either accept the connection (and start streaming)
or close with the corresponding WS status code.

Subscriptions are managed by `notification_tool`:
- `/ws/incidents/{id}` subscribes to that incident's stream + admin firehose
  (admin subscribers receive every incident's events plus PROVIDER_LOCATION).
- `/ws/admin/live` subscribes to the admin firehose only.

A subscriber's callback writes the event JSON straight into the WebSocket.
On disconnect, the subscription is removed so callbacks don't accumulate.
"""
from __future__ import annotations

import asyncio
import uuid
from typing import Annotated, Any

from fastapi import APIRouter, Query, WebSocket, WebSocketDisconnect, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import AsyncSessionLocal
from app.middleware.logging import get_logger
from app.models.enums import UserRole
from app.models.user import User
from app.services.jwt_service import InvalidTokenError, decode_token
from app.tools.notification_tool import (
    subscribe_admin,
    subscribe_incident,
    subscriber_counts,
)

log = get_logger("api.ws")
router = APIRouter(tags=["websocket"])


# ----------------------------------------------------------------------
# WS auth helper
# ----------------------------------------------------------------------


async def _authenticate(token: str | None) -> User | None:
    """Decode the bearer token + look up the user. Returns None on any failure."""
    if not token:
        return None
    try:
        payload = decode_token(token, expected_type="access")
        user_id = uuid.UUID(payload.sub)
    except (InvalidTokenError, ValueError):
        return None

    async with AsyncSessionLocal() as session:
        user = await session.get(User, user_id)
        if user is None or not user.is_active:
            return None
        return user


# ----------------------------------------------------------------------
# /ws/incidents/{incident_id}
# ----------------------------------------------------------------------


@router.websocket("/ws/incidents/{incident_id}")
async def incident_stream(
    websocket: WebSocket,
    incident_id: uuid.UUID,
    token: Annotated[str | None, Query()] = None,
) -> None:
    user = await _authenticate(token)
    if user is None:
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION,
                              reason="invalid or missing token")
        return

    # Verify the user actually has access to this incident: must be customer,
    # provider, or admin on the row.
    if user.role != UserRole.admin.value:
        async with AsyncSessionLocal() as session:
            from app.tools.db_read_tool import get_incident
            incident = await get_incident(session, incident_id)
            if incident is None:
                await websocket.close(code=status.WS_1008_POLICY_VIOLATION,
                                      reason="incident not found")
                return
            owner = (
                (user.role == UserRole.customer.value and incident.customer_id == user.id)
                or (user.role == UserRole.provider.value and incident.provider_id == user.id)
            )
            if not owner:
                await websocket.close(code=status.WS_1008_POLICY_VIOLATION,
                                      reason="not your incident")
                return

    await websocket.accept()
    log.info("ws_incident_connected",
             incident_id=str(incident_id), user_id=str(user.id),
             counts=subscriber_counts())

    queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue(maxsize=200)

    async def _push(payload: dict[str, Any]) -> None:
        # Use a queue so slow socket writes don't block the broker fanout.
        try:
            queue.put_nowait(payload)
        except asyncio.QueueFull:
            log.warning("ws_queue_full_dropping", incident_id=str(incident_id))

    unsub = subscribe_incident(incident_id, _push)

    try:
        # Send an initial hello so the client knows the connection is live
        await websocket.send_json({
            "event": "CONNECTED",
            "incident_id": str(incident_id),
            "data": {"role": user.role},
        })

        async def _writer() -> None:
            while True:
                payload = await queue.get()
                await websocket.send_json(payload)

        async def _reader() -> None:
            # Drain inbound frames so the client can ping/disconnect cleanly
            while True:
                await websocket.receive_text()

        await asyncio.gather(_writer(), _reader())
    except WebSocketDisconnect:
        pass
    except Exception as exc:  # noqa: BLE001
        log.warning("ws_incident_error", error=str(exc))
    finally:
        unsub()
        log.info("ws_incident_disconnected", incident_id=str(incident_id),
                 user_id=str(user.id))


# ----------------------------------------------------------------------
# /ws/admin/live
# ----------------------------------------------------------------------


@router.websocket("/ws/admin/live")
async def admin_live(
    websocket: WebSocket,
    token: Annotated[str | None, Query()] = None,
) -> None:
    user = await _authenticate(token)
    if user is None or user.role != UserRole.admin.value:
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION,
                              reason="admin only")
        return

    await websocket.accept()
    log.info("ws_admin_connected", user_id=str(user.id), counts=subscriber_counts())

    queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue(maxsize=500)

    async def _push(payload: dict[str, Any]) -> None:
        try:
            queue.put_nowait(payload)
        except asyncio.QueueFull:
            log.warning("ws_admin_queue_full_dropping")

    unsub = subscribe_admin(_push)

    try:
        await websocket.send_json({"event": "CONNECTED", "scope": "admin"})

        async def _writer() -> None:
            while True:
                payload = await queue.get()
                await websocket.send_json(payload)

        async def _reader() -> None:
            while True:
                await websocket.receive_text()

        await asyncio.gather(_writer(), _reader())
    except WebSocketDisconnect:
        pass
    except Exception as exc:  # noqa: BLE001
        log.warning("ws_admin_error", error=str(exc))
    finally:
        unsub()
        log.info("ws_admin_disconnected", user_id=str(user.id))

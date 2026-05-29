"""Read-only DB access for agents.

Agents that need to inspect users, incidents, providers, or task history go
through these helpers instead of constructing queries themselves. This:
- Centralizes the queries so we can add observability / caching uniformly.
- Keeps agent code small and focused on reasoning.
- Makes it obvious in code review what an agent reads vs. writes.
"""
from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.middleware.logging import get_logger
from app.models.enums import UserRole
from app.models.incident import Incident
from app.models.message import Message
from app.models.provider import Provider
from app.models.task_log import TaskLog
from app.models.user import User

log = get_logger("tools.db_read")


# ----------------------------------------------------------------------
# Reads
# ----------------------------------------------------------------------


async def get_incident(db: AsyncSession, incident_id: uuid.UUID) -> Incident | None:
    return await db.get(Incident, incident_id)


async def get_user(db: AsyncSession, user_id: uuid.UUID) -> User | None:
    return await db.get(User, user_id)


async def get_provider(db: AsyncSession, provider_id: uuid.UUID) -> Provider | None:
    return await db.get(Provider, provider_id)


async def get_active_admins(db: AsyncSession, limit: int = 10) -> list[User]:
    """Return the active admin users — used by EscalationAgent to broadcast alerts."""
    result = await db.execute(
        select(User)
        .where(User.role == UserRole.admin.value)
        .where(User.is_active.is_(True))
        .limit(limit)
    )
    return list(result.scalars())


async def get_recent_task_logs(
    db: AsyncSession,
    *,
    incident_id: uuid.UUID,
    limit: int = 50,
) -> list[TaskLog]:
    """Last N agent steps for an incident, newest first."""
    result = await db.execute(
        select(TaskLog)
        .where(TaskLog.incident_id == incident_id)
        .order_by(TaskLog.created_at.desc())
        .limit(limit)
    )
    return list(result.scalars())


async def get_recent_messages(
    db: AsyncSession,
    *,
    incident_id: uuid.UUID,
    limit: int = 20,
) -> list[Message]:
    """Communications log for an incident, newest first."""
    result = await db.execute(
        select(Message)
        .where(Message.incident_id == incident_id)
        .order_by(Message.created_at.desc())
        .limit(limit)
    )
    return list(result.scalars())

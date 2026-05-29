"""Incident model — the heart of the system. Tracks an incident from REPORTED to CLOSED."""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING, Any

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, Numeric, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base
from app.models.enums import IncidentStatus

if TYPE_CHECKING:
    from app.models.message import Message
    from app.models.task_log import TaskLog
    from app.models.user import User


class Incident(Base):
    __tablename__ = "incidents"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    customer_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=False, index=True
    )
    provider_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=True, index=True
    )
    status: Mapped[IncidentStatus] = mapped_column(
        String(20),
        default=IncidentStatus.REPORTED.value,
        nullable=False,
        index=True,
    )
    lat: Mapped[float] = mapped_column(Numeric(10, 7), nullable=False)
    lng: Mapped[float] = mapped_column(Numeric(10, 7), nullable=False)
    address: Mapped[str | None] = mapped_column(Text, nullable=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    image_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    voice_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    ai_diagnosis: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    eta_minutes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    guardrail_flagged: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False, index=True
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )
    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    # Relationships
    customer: Mapped["User"] = relationship(
        "User",
        back_populates="incidents_as_customer",
        foreign_keys=[customer_id],
    )
    provider: Mapped["User | None"] = relationship(
        "User",
        back_populates="incidents_as_provider",
        foreign_keys=[provider_id],
    )
    messages: Mapped[list["Message"]] = relationship(
        "Message", back_populates="incident", cascade="all, delete-orphan"
    )
    task_logs: Mapped[list["TaskLog"]] = relationship(
        "TaskLog", back_populates="incident", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:
        return f"<Incident {self.id} status={self.status}>"

"""SecurityEvent model — every blocked prompt injection or abuse attempt."""
from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import ARRAY, DateTime, ForeignKey, String, Text, TypeDecorator, func
from sqlalchemy.dialects.postgresql import INET, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base
from app.models.enums import SecurityEventType


class _INETAsString(TypeDecorator):
    """Postgres INET column whose Python value is always a plain string.

    asyncpg returns `ipaddress.IPv4Address` / `IPv6Address` for INET columns by
    default. That makes equality checks like `event.ip_address == "10.0.0.1"`
    fail (IPv4Address('10.0.0.1') != '10.0.0.1'). We don't use any INET-specific
    behavior, so just coerce to str on the way out.
    """

    impl = INET
    cache_ok = True

    def process_result_value(self, value, dialect):  # noqa: ARG002
        return str(value) if value is not None else None


class SecurityEvent(Base):
    __tablename__ = "security_events"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    event_type: Mapped[SecurityEventType] = mapped_column(String(30), nullable=False)
    # raw_input is stored encrypted in app code; column itself is plain text
    raw_input: Mapped[str | None] = mapped_column(Text, nullable=True)
    flagged_patterns: Mapped[list[str] | None] = mapped_column(ARRAY(Text), nullable=True)
    ip_address: Mapped[str | None] = mapped_column(_INETAsString, nullable=True)
    user_agent: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False, index=True
    )

    def __repr__(self) -> str:
        return f"<SecurityEvent {self.event_type} user={self.user_id}>"

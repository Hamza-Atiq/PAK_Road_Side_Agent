"""Message model — audit log of every communication sent (SMS, WhatsApp, WebSocket)."""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, ForeignKey, String, Text, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base
from app.models.enums import DeliveryStatus, MessageType

if TYPE_CHECKING:
    from app.models.incident import Incident


class Message(Base):
    __tablename__ = "messages"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    incident_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("incidents.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )
    sender_agent: Mapped[str | None] = mapped_column(String(50), nullable=True)
    msg_type: Mapped[MessageType] = mapped_column(String(20), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    recipient_phone: Mapped[str | None] = mapped_column(String(20), nullable=True)
    twilio_sid: Mapped[str | None] = mapped_column(String(50), nullable=True, index=True)
    delivery_status: Mapped[DeliveryStatus] = mapped_column(
        String(20), default=DeliveryStatus.PENDING.value, nullable=False
    )
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    delivered_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    # Relationships
    incident: Mapped["Incident | None"] = relationship("Incident", back_populates="messages")

    def __repr__(self) -> str:
        return f"<Message {self.msg_type} -> {self.recipient_phone} [{self.delivery_status}]>"

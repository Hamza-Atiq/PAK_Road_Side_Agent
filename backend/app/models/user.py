"""User model — base account for customer, provider, and admin roles."""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, CheckConstraint, DateTime, Integer, String, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base
from app.models.enums import UserRole

if TYPE_CHECKING:
    from app.models.incident import Incident
    from app.models.provider import Provider


class User(Base):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    phone: Mapped[str] = mapped_column(String(20), unique=True, nullable=False, index=True)
    email: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    role: Mapped[UserRole] = mapped_column(String(20), nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    is_phone_verified: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    abuse_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    # Relationships
    provider_profile: Mapped["Provider | None"] = relationship(
        "Provider",
        back_populates="user",
        uselist=False,
        cascade="all, delete-orphan",
    )
    incidents_as_customer: Mapped[list["Incident"]] = relationship(
        "Incident",
        back_populates="customer",
        foreign_keys="Incident.customer_id",
    )
    incidents_as_provider: Mapped[list["Incident"]] = relationship(
        "Incident",
        back_populates="provider",
        foreign_keys="Incident.provider_id",
    )

    __table_args__ = (
        CheckConstraint(
            "role IN ('customer','provider','admin')",
            name="users_role_check",
        ),
    )

    def __repr__(self) -> str:
        return f"<User {self.role}:{self.phone}>"

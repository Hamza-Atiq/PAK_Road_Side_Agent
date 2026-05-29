"""Initial schema — all tables, enums, extensions, indexes.

Revision ID: 0001
Revises:
Create Date: 2026-05-23

Creates:
- Extensions: postgis, pgcrypto, pg_trgm
- Enums: incident_status, msg_type, dlv_status, security_event_type, etc. (stored as VARCHAR with CHECK)
- Tables: users, providers, incidents, messages, task_logs, security_events
- Indexes: GiST on providers.location, partial idx on is_available, BTREE indexes on FKs
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from geoalchemy2 import Geography
from sqlalchemy.dialects import postgresql

revision: str = "0001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# Enum value lists (kept in sync with app.models.enums)
USER_ROLES = ("customer", "provider", "admin")
INCIDENT_STATUSES = (
    "REPORTED", "ANALYZING", "ASSIGNED", "NO_PROVIDER", "ESCALATED",
    "EN_ROUTE", "ARRIVED", "COMPLETED", "CLOSED",
)
MSG_TYPES = ("SMS", "WHATSAPP", "WEBSOCKET", "SYSTEM")
DLV_STATUSES = ("PENDING", "SENT", "DELIVERED", "FAILED")
TASK_LOG_STATUSES = ("STARTED", "SUCCESS", "FAILURE", "RETRY")
SECURITY_EVENT_TYPES = ("INJECTION_ATTEMPT", "ABUSE_FLAGGED", "RATE_LIMITED", "SUSPENDED")


def _check(col: str, values: tuple[str, ...]) -> str:
    """Helper: build a CHECK constraint expression for an enum-as-VARCHAR column."""
    quoted = ",".join(f"'{v}'" for v in values)
    return f"{col} IN ({quoted})"


def upgrade() -> None:
    # ----- Extensions -----
    op.execute("CREATE EXTENSION IF NOT EXISTS postgis;")
    op.execute("CREATE EXTENSION IF NOT EXISTS pgcrypto;")
    op.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm;")

    # ----- users -----
    op.create_table(
        "users",
        sa.Column("id", postgresql.UUID(as_uuid=True),
                  server_default=sa.text("gen_random_uuid()"), primary_key=True),
        sa.Column("phone", sa.String(20), nullable=False, unique=True),
        sa.Column("email", sa.String(255), nullable=True),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("role", sa.String(20), nullable=False),
        sa.Column("password_hash", sa.String(255), nullable=False),
        sa.Column("is_active", sa.Boolean, nullable=False, server_default=sa.text("false")),
        sa.Column("is_phone_verified", sa.Boolean, nullable=False, server_default=sa.text("false")),
        sa.Column("abuse_count", sa.Integer, nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True),
                  nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True),
                  nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint(_check("role", USER_ROLES), name="users_role_check"),
    )
    op.create_index("ix_users_phone", "users", ["phone"], unique=True)
    op.create_index("ix_users_email", "users", ["email"])

    # ----- providers -----
    op.create_table(
        "providers",
        sa.Column("id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("users.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("service_type", sa.String(50), nullable=False),
        sa.Column("vehicle_info", sa.Text, nullable=True),
        sa.Column("is_available", sa.Boolean, nullable=False, server_default=sa.text("false")),
        sa.Column("is_approved", sa.Boolean, nullable=False, server_default=sa.text("false")),
        sa.Column("location", Geography(geometry_type="POINT", srid=4326), nullable=True),
        sa.Column("last_ping", sa.DateTime(timezone=True), nullable=True),
        sa.Column("total_jobs", sa.Integer, nullable=False, server_default="0"),
    )
    # GiST index for KNN nearest-provider queries (<-> operator)
    op.execute("CREATE INDEX providers_location_gist ON providers USING GIST (location);")
    # Partial index — only available providers (cheap to scan when dispatching)
    op.execute(
        "CREATE INDEX providers_available_idx ON providers (is_available) "
        "WHERE is_available = TRUE;"
    )

    # ----- incidents -----
    op.create_table(
        "incidents",
        sa.Column("id", postgresql.UUID(as_uuid=True),
                  server_default=sa.text("gen_random_uuid()"), primary_key=True),
        sa.Column("customer_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("users.id"), nullable=False),
        sa.Column("provider_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("users.id"), nullable=True),
        sa.Column("status", sa.String(20), nullable=False, server_default="REPORTED"),
        sa.Column("lat", sa.Numeric(10, 7), nullable=False),
        sa.Column("lng", sa.Numeric(10, 7), nullable=False),
        sa.Column("address", sa.Text, nullable=True),
        sa.Column("description", sa.Text, nullable=True),
        sa.Column("image_url", sa.Text, nullable=True),
        sa.Column("voice_url", sa.Text, nullable=True),
        sa.Column("ai_diagnosis", postgresql.JSONB, nullable=True),
        sa.Column("eta_minutes", sa.Integer, nullable=True),
        sa.Column("guardrail_flagged", sa.Boolean, nullable=False, server_default=sa.text("false")),
        sa.Column("created_at", sa.DateTime(timezone=True),
                  nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True),
                  nullable=False, server_default=sa.func.now()),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(_check("status", INCIDENT_STATUSES), name="incidents_status_check"),
    )
    op.create_index("ix_incidents_customer_id", "incidents", ["customer_id"])
    op.create_index("ix_incidents_provider_id", "incidents", ["provider_id"])
    op.create_index("ix_incidents_status", "incidents", ["status"])
    op.create_index("ix_incidents_created_at", "incidents", [sa.text("created_at DESC")])

    # ----- messages -----
    op.create_table(
        "messages",
        sa.Column("id", postgresql.UUID(as_uuid=True),
                  server_default=sa.text("gen_random_uuid()"), primary_key=True),
        sa.Column("incident_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("incidents.id", ondelete="CASCADE"), nullable=True),
        sa.Column("sender_agent", sa.String(50), nullable=True),
        sa.Column("msg_type", sa.String(20), nullable=False),
        sa.Column("content", sa.Text, nullable=False),
        sa.Column("recipient_phone", sa.String(20), nullable=True),
        sa.Column("twilio_sid", sa.String(50), nullable=True),
        sa.Column("delivery_status", sa.String(20), nullable=False, server_default="PENDING"),
        sa.Column("error_message", sa.Text, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True),
                  nullable=False, server_default=sa.func.now()),
        sa.Column("delivered_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(_check("msg_type", MSG_TYPES), name="messages_type_check"),
        sa.CheckConstraint(_check("delivery_status", DLV_STATUSES),
                           name="messages_delivery_check"),
    )
    op.create_index("ix_messages_incident_id", "messages", ["incident_id"])
    op.create_index("ix_messages_twilio_sid", "messages", ["twilio_sid"])

    # ----- task_logs -----
    op.create_table(
        "task_logs",
        sa.Column("id", postgresql.UUID(as_uuid=True),
                  server_default=sa.text("gen_random_uuid()"), primary_key=True),
        sa.Column("incident_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("incidents.id", ondelete="CASCADE"), nullable=True),
        sa.Column("agent_name", sa.String(50), nullable=False),
        sa.Column("step", sa.String(100), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("reasoning", sa.Text, nullable=True),
        sa.Column("payload", postgresql.JSONB, nullable=True),
        sa.Column("error", sa.Text, nullable=True),
        sa.Column("duration_ms", sa.Integer, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True),
                  nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint(_check("status", TASK_LOG_STATUSES), name="task_logs_status_check"),
    )
    op.create_index("ix_task_logs_incident_id", "task_logs", ["incident_id"])
    op.create_index("ix_task_logs_agent_name", "task_logs", ["agent_name"])
    op.create_index("ix_task_logs_created_at", "task_logs", [sa.text("created_at DESC")])

    # ----- security_events -----
    op.create_table(
        "security_events",
        sa.Column("id", postgresql.UUID(as_uuid=True),
                  server_default=sa.text("gen_random_uuid()"), primary_key=True),
        sa.Column("user_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("event_type", sa.String(30), nullable=False),
        sa.Column("raw_input", sa.Text, nullable=True),
        sa.Column("flagged_patterns", postgresql.ARRAY(sa.Text), nullable=True),
        sa.Column("ip_address", postgresql.INET, nullable=True),
        sa.Column("user_agent", sa.Text, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True),
                  nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint(_check("event_type", SECURITY_EVENT_TYPES),
                           name="security_events_type_check"),
    )
    op.create_index(
        "ix_security_events_user_created", "security_events",
        ["user_id", sa.text("created_at DESC")],
    )


def downgrade() -> None:
    op.drop_index("ix_security_events_user_created", table_name="security_events")
    op.drop_table("security_events")

    op.drop_index("ix_task_logs_created_at", table_name="task_logs")
    op.drop_index("ix_task_logs_agent_name", table_name="task_logs")
    op.drop_index("ix_task_logs_incident_id", table_name="task_logs")
    op.drop_table("task_logs")

    op.drop_index("ix_messages_twilio_sid", table_name="messages")
    op.drop_index("ix_messages_incident_id", table_name="messages")
    op.drop_table("messages")

    op.drop_index("ix_incidents_created_at", table_name="incidents")
    op.drop_index("ix_incidents_status", table_name="incidents")
    op.drop_index("ix_incidents_provider_id", table_name="incidents")
    op.drop_index("ix_incidents_customer_id", table_name="incidents")
    op.drop_table("incidents")

    op.execute("DROP INDEX IF EXISTS providers_available_idx;")
    op.execute("DROP INDEX IF EXISTS providers_location_gist;")
    op.drop_table("providers")

    op.drop_index("ix_users_email", table_name="users")
    op.drop_index("ix_users_phone", table_name="users")
    op.drop_table("users")

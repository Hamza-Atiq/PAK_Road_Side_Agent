"""Enum types shared across models."""
from __future__ import annotations

import enum


class UserRole(str, enum.Enum):
    customer = "customer"
    provider = "provider"
    admin = "admin"


class ServiceType(str, enum.Enum):
    mechanic = "mechanic"
    tow_truck = "tow_truck"
    tire = "tire"
    battery = "battery"
    fuel = "fuel"
    locksmith = "locksmith"
    other = "other"


class IncidentStatus(str, enum.Enum):
    REPORTED = "REPORTED"
    ANALYZING = "ANALYZING"
    ASSIGNED = "ASSIGNED"
    NO_PROVIDER = "NO_PROVIDER"
    ESCALATED = "ESCALATED"
    EN_ROUTE = "EN_ROUTE"
    ARRIVED = "ARRIVED"
    COMPLETED = "COMPLETED"
    CLOSED = "CLOSED"


class IncidentSeverity(str, enum.Enum):
    low = "low"
    medium = "medium"
    high = "high"
    critical = "critical"
    unknown = "unknown"


class MessageType(str, enum.Enum):
    SMS = "SMS"
    WHATSAPP = "WHATSAPP"
    WEBSOCKET = "WEBSOCKET"
    SYSTEM = "SYSTEM"


class DeliveryStatus(str, enum.Enum):
    PENDING = "PENDING"
    SENT = "SENT"
    DELIVERED = "DELIVERED"
    FAILED = "FAILED"


class TaskLogStatus(str, enum.Enum):
    STARTED = "STARTED"
    SUCCESS = "SUCCESS"
    FAILURE = "FAILURE"
    RETRY = "RETRY"


class SecurityEventType(str, enum.Enum):
    INJECTION_ATTEMPT = "INJECTION_ATTEMPT"
    ABUSE_FLAGGED = "ABUSE_FLAGGED"
    RATE_LIMITED = "RATE_LIMITED"
    SUSPENDED = "SUSPENDED"

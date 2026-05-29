"""Tests for EscalationAgent and TrackingAgent (mocked sub-agents + real DB)."""
from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.agents.base import AgentContext, AgentResult
from app.agents.communication import CommunicationResult
from app.agents.dispatch import DispatchResult
from app.agents.escalation import (
    EscalationAgent,
    EscalationOutcome,
    EscalationReason,
)
from app.agents.tracking import (
    TrackingAgent,
    _find_offline_provider_incidents,
    _find_stalled_assignments,
    _find_stalled_en_route,
)
from app.models.enums import IncidentStatus, UserRole
from app.models.incident import Incident
from app.models.provider import Provider
from app.models.user import User
from app.services.security import hash_password


# ============================================================
# Helpers
# ============================================================


def _stub_agent(name: str, output, error=None) -> AsyncMock:
    a = MagicMock()
    a.name = name
    a.run = AsyncMock(return_value=AgentResult(
        success=error is None, output=output, error=error, agent_name=name,
    ))
    return a


async def _make_user(db_session, *, role, phone, name="X"):
    u = User(
        phone=phone, name=name, role=role.value,
        password_hash=hash_password("password123"),
        is_active=True, is_phone_verified=True,
    )
    db_session.add(u)
    await db_session.flush()
    return u


async def _make_provider_full(db_session, *, phone, lat=37.77, lng=-122.42,
                              service_type="mechanic", last_ping=None):
    user = await _make_user(db_session, role=UserRole.provider, phone=phone, name="P")
    p = Provider(
        id=user.id, service_type=service_type,
        is_available=False, is_approved=True, total_jobs=5,
        location=f"SRID=4326;POINT({lng} {lat})",
        last_ping=last_ping,
    )
    db_session.add(p)
    await db_session.flush()
    return user, p


async def _make_incident_at_status(
    db_session, *, customer_id, provider_id=None, status=IncidentStatus.ASSIGNED,
    updated_minutes_ago=0,
):
    inc = Incident(
        customer_id=customer_id, provider_id=provider_id,
        lat=37.7749, lng=-122.4194, description="test", status=status.value,
    )
    db_session.add(inc)
    await db_session.flush()
    if updated_minutes_ago:
        inc.updated_at = datetime.now(UTC) - timedelta(minutes=updated_minutes_ago)
        await db_session.flush()
    return inc


# ============================================================
# EscalationAgent — input validation (no DB needed)
# ============================================================


@pytest.mark.asyncio
async def test_escalation_requires_incident_id():
    agent = EscalationAgent(anthropic_client=MagicMock())
    ctx = AgentContext(db=MagicMock(), incident_id=None,
                       payload={"reason": "NO_PROVIDER"})
    result = await agent.run(ctx)
    assert result.success is False
    assert "incident_id" in result.error.lower()


@pytest.mark.asyncio
async def test_escalation_rejects_unknown_reason(db_session):
    """Test the reason validation by passing through a real session so we
    reach the validation branch (not the missing-incident_id branch)."""
    customer = await _make_user(db_session, role=UserRole.customer, phone="+15554440000")
    incident = await _make_incident_at_status(
        db_session, customer_id=customer.id, status=IncidentStatus.ASSIGNED,
    )
    agent = EscalationAgent(anthropic_client=MagicMock())
    ctx = AgentContext(db=db_session, incident_id=incident.id,
                       payload={"reason": "MADE_UP"})
    result = await agent.run(ctx)
    assert result.success is False
    assert "unknown escalation reason" in result.error.lower()


# ============================================================
# EscalationAgent — NO_PROVIDER alerts admin
# ============================================================


@pytest.mark.asyncio
async def test_no_provider_escalation_alerts_admin(db_session):
    customer = await _make_user(db_session, role=UserRole.customer, phone="+15554441001")
    admin = await _make_user(db_session, role=UserRole.admin, phone="+15554441099", name="Admin")
    incident = await _make_incident_at_status(
        db_session, customer_id=customer.id, status=IncidentStatus.ANALYZING,
    )
    comm = _stub_agent(
        "CommunicationAgent",
        CommunicationResult(sent=True, channel="sms", content="alert", reason="ok"),
    )
    agent = EscalationAgent(
        anthropic_client=MagicMock(),
        dispatch=_stub_agent("DispatchAgent", DispatchResult(assigned=False)),
        communication=comm,
    )
    ctx = AgentContext(
        db=db_session, incident_id=incident.id,
        payload={"reason": EscalationReason.NO_PROVIDER.value, "radius_used_km": 100},
    )
    result = await agent.run(ctx)
    assert result.success, result.error
    outcome: EscalationOutcome = result.output
    assert outcome.admin_alerted is True
    assert outcome.new_status == IncidentStatus.NO_PROVIDER.value
    await db_session.refresh(incident)
    assert incident.status == IncidentStatus.NO_PROVIDER.value


# ============================================================
# EscalationAgent — PROVIDER_OFFLINE triggers redispatch
# ============================================================


@pytest.mark.asyncio
async def test_provider_offline_releases_and_redispatches(db_session):
    customer = await _make_user(db_session, role=UserRole.customer, phone="+15554442001")
    old_user, old_provider = await _make_provider_full(
        db_session, phone="+15554442002", lat=37.7749, lng=-122.4194,
    )
    old_provider.is_available = False  # currently on the job

    incident = await _make_incident_at_status(
        db_session, customer_id=customer.id, provider_id=old_user.id,
        status=IncidentStatus.ASSIGNED,
    )

    new_provider_id = uuid.uuid4()
    dispatch = _stub_agent("DispatchAgent", DispatchResult(
        assigned=True, provider_id=new_provider_id, provider_name="Backup Tow",
        eta_minutes=12, distance_km=2.5, candidates_considered=1, radius_used_km=50.0,
    ))
    comm = _stub_agent("CommunicationAgent", CommunicationResult(
        sent=True, channel="sms", content="ok", reason="ok",
    ))

    agent = EscalationAgent(
        anthropic_client=MagicMock(), dispatch=dispatch, communication=comm,
    )
    ctx = AgentContext(
        db=db_session, incident_id=incident.id,
        payload={"reason": EscalationReason.PROVIDER_OFFLINE.value},
    )
    result = await agent.run(ctx)
    assert result.success, result.error
    outcome = result.output
    assert outcome.redispatched is True
    assert outcome.new_provider_id == new_provider_id
    # Old provider made available again
    await db_session.refresh(old_provider)
    assert old_provider.is_available is True


@pytest.mark.asyncio
async def test_provider_offline_redispatch_failure_alerts_admin(db_session):
    customer = await _make_user(db_session, role=UserRole.customer, phone="+15554443001")
    admin = await _make_user(db_session, role=UserRole.admin, phone="+15554443099", name="Admin")
    old_user, _ = await _make_provider_full(db_session, phone="+15554443002")
    incident = await _make_incident_at_status(
        db_session, customer_id=customer.id, provider_id=old_user.id,
        status=IncidentStatus.ASSIGNED,
    )

    dispatch = _stub_agent("DispatchAgent", DispatchResult(assigned=False))
    comm = _stub_agent("CommunicationAgent", CommunicationResult(
        sent=True, channel="sms", content="alert", reason="ok",
    ))
    agent = EscalationAgent(
        anthropic_client=MagicMock(), dispatch=dispatch, communication=comm,
    )
    ctx = AgentContext(
        db=db_session, incident_id=incident.id,
        payload={"reason": EscalationReason.PROVIDER_OFFLINE.value},
    )
    result = await agent.run(ctx)
    assert result.success
    assert result.output.redispatched is False
    assert result.output.admin_alerted is True


# ============================================================
# EscalationAgent — STALLED_EN_ROUTE alerts only
# ============================================================


@pytest.mark.asyncio
async def test_stalled_en_route_alerts_admin_does_not_reassign(db_session):
    customer = await _make_user(db_session, role=UserRole.customer, phone="+15554444001")
    admin = await _make_user(db_session, role=UserRole.admin, phone="+15554444099", name="Admin")
    prov_user, _ = await _make_provider_full(db_session, phone="+15554444002")
    incident = await _make_incident_at_status(
        db_session, customer_id=customer.id, provider_id=prov_user.id,
        status=IncidentStatus.EN_ROUTE,
    )

    dispatch_should_not_run = _stub_agent("DispatchAgent", None)
    comm = _stub_agent("CommunicationAgent", CommunicationResult(
        sent=True, channel="sms", content="alert", reason="ok",
    ))
    agent = EscalationAgent(
        anthropic_client=MagicMock(),
        dispatch=dispatch_should_not_run, communication=comm,
    )
    ctx = AgentContext(
        db=db_session, incident_id=incident.id,
        payload={"reason": EscalationReason.STALLED_EN_ROUTE.value},
    )
    result = await agent.run(ctx)
    assert result.success
    assert result.output.redispatched is False
    assert result.output.admin_alerted is True
    # Status should NOT have been changed
    await db_session.refresh(incident)
    assert incident.status == IncidentStatus.EN_ROUTE.value
    # Dispatch must NOT have been called
    assert dispatch_should_not_run.run.call_count == 0


# ============================================================
# EscalationAgent — REPEATED_FAILURE marks ESCALATED
# ============================================================


@pytest.mark.asyncio
async def test_repeated_failure_transitions_to_escalated(db_session):
    customer = await _make_user(db_session, role=UserRole.customer, phone="+15554445001")
    admin = await _make_user(db_session, role=UserRole.admin, phone="+15554445099", name="Admin")
    incident = await _make_incident_at_status(
        db_session, customer_id=customer.id, status=IncidentStatus.ANALYZING,
    )
    comm = _stub_agent("CommunicationAgent", CommunicationResult(
        sent=True, channel="sms", content="alert", reason="ok",
    ))
    agent = EscalationAgent(
        anthropic_client=MagicMock(),
        dispatch=_stub_agent("DispatchAgent", DispatchResult(assigned=False)),
        communication=comm,
    )
    ctx = AgentContext(
        db=db_session, incident_id=incident.id,
        payload={
            "reason": EscalationReason.REPEATED_FAILURE.value,
            "summary": "3 sub-agent failures",
        },
    )
    result = await agent.run(ctx)
    assert result.success
    assert result.output.new_status == IncidentStatus.ESCALATED.value
    await db_session.refresh(incident)
    assert incident.status == IncidentStatus.ESCALATED.value


# ============================================================
# TrackingAgent — detection queries (real DB)
# ============================================================


@pytest.mark.asyncio
async def test_tracking_detects_provider_offline(db_session):
    customer = await _make_user(db_session, role=UserRole.customer, phone="+15554446001")
    old_ping = datetime.now(UTC) - timedelta(minutes=5)
    prov_user, _ = await _make_provider_full(
        db_session, phone="+15554446002", last_ping=old_ping,
    )
    incident = await _make_incident_at_status(
        db_session, customer_id=customer.id, provider_id=prov_user.id,
        status=IncidentStatus.EN_ROUTE,
    )
    offline = await _find_offline_provider_incidents(db_session, ping_threshold_seconds=90)
    assert any(i.id == incident.id for i in offline)


@pytest.mark.asyncio
async def test_tracking_treats_null_last_ping_as_offline(db_session):
    customer = await _make_user(db_session, role=UserRole.customer, phone="+15554447001")
    prov_user, _ = await _make_provider_full(
        db_session, phone="+15554447002", last_ping=None,
    )
    incident = await _make_incident_at_status(
        db_session, customer_id=customer.id, provider_id=prov_user.id,
        status=IncidentStatus.ASSIGNED,
    )
    offline = await _find_offline_provider_incidents(db_session, ping_threshold_seconds=90)
    assert any(i.id == incident.id for i in offline)


@pytest.mark.asyncio
async def test_tracking_ignores_fresh_pings(db_session):
    customer = await _make_user(db_session, role=UserRole.customer, phone="+15554448001")
    fresh = datetime.now(UTC) - timedelta(seconds=10)
    prov_user, _ = await _make_provider_full(
        db_session, phone="+15554448002", last_ping=fresh,
    )
    incident = await _make_incident_at_status(
        db_session, customer_id=customer.id, provider_id=prov_user.id,
        status=IncidentStatus.EN_ROUTE,
    )
    offline = await _find_offline_provider_incidents(db_session, ping_threshold_seconds=90)
    assert not any(i.id == incident.id for i in offline)


@pytest.mark.asyncio
async def test_tracking_detects_stalled_assignment(db_session):
    customer = await _make_user(db_session, role=UserRole.customer, phone="+15554449001")
    prov_user, _ = await _make_provider_full(db_session, phone="+15554449002")
    incident = await _make_incident_at_status(
        db_session, customer_id=customer.id, provider_id=prov_user.id,
        status=IncidentStatus.ASSIGNED, updated_minutes_ago=75,
    )
    stalled = await _find_stalled_assignments(db_session, assigned_timeout_minutes=60)
    assert any(i.id == incident.id for i in stalled)


@pytest.mark.asyncio
async def test_tracking_detects_stalled_en_route(db_session):
    customer = await _make_user(db_session, role=UserRole.customer, phone="+15554450001")
    prov_user, _ = await _make_provider_full(db_session, phone="+15554450002")
    incident = await _make_incident_at_status(
        db_session, customer_id=customer.id, provider_id=prov_user.id,
        status=IncidentStatus.EN_ROUTE, updated_minutes_ago=200,
    )
    stalled = await _find_stalled_en_route(db_session, en_route_timeout_minutes=180)
    assert any(i.id == incident.id for i in stalled)


@pytest.mark.asyncio
async def test_tracking_agent_scan_triggers_escalation(db_session):
    customer = await _make_user(db_session, role=UserRole.customer, phone="+15554451001")
    prov_user, _ = await _make_provider_full(
        db_session, phone="+15554451002",
        last_ping=datetime.now(UTC) - timedelta(minutes=5),
    )
    incident = await _make_incident_at_status(
        db_session, customer_id=customer.id, provider_id=prov_user.id,
        status=IncidentStatus.EN_ROUTE,
    )

    # Track Escalation calls without running the real chain
    escalation = MagicMock()
    escalation.run = AsyncMock(return_value=AgentResult(
        success=True, output=EscalationOutcome(
            reason="PROVIDER_OFFLINE", incident_id=incident.id,
            new_status="NO_PROVIDER", redispatched=False,
            new_provider_id=None, admin_alerted=True, notes="ok",
        ),
        agent_name="EscalationAgent",
    ))

    agent = TrackingAgent(anthropic_client=MagicMock(), escalation=escalation)
    ctx = AgentContext(db=db_session)
    result = await agent.run(ctx)
    assert result.success
    summary = result.output
    assert summary.offline_provider_count >= 1
    assert summary.escalations_triggered >= 1
    assert incident.id in summary.incident_ids_escalated


@pytest.mark.asyncio
async def test_tracking_agent_no_anomalies_no_escalations(db_session):
    """Clean slate → zero escalations."""
    agent = TrackingAgent(
        anthropic_client=MagicMock(),
        escalation=_stub_agent("EscalationAgent", None),
    )
    ctx = AgentContext(db=db_session)
    result = await agent.run(ctx)
    assert result.success
    assert result.output.escalations_triggered == 0


@pytest.mark.asyncio
async def test_escalation_agent_tool_allow_list():
    """EscalationAgent must have the tools it actually uses + nothing more."""
    agent = EscalationAgent(anthropic_client=MagicMock())
    # Tools the handlers genuinely need
    assert "db_write_tool" in agent.tools
    assert "twilio_tool" in agent.tools
    assert "spawn_agent" in agent.tools
    # Specifically NOT in the allow list:
    from app.agents.base import ToolNotAuthorizedError
    for forbidden in ("vision_tool", "transcription_tool"):
        with pytest.raises(ToolNotAuthorizedError):
            agent._check_tool_authorized(forbidden)

"""Tests for geo_service, routing_tool, db_write_tool, and DispatchAgent."""
from __future__ import annotations

import json
import os
import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.agents.base import AgentContext
from app.agents.dispatch import DispatchAgent, DispatchResult
from app.models.enums import IncidentStatus, UserRole
from app.models.incident import Incident
from app.services.geo_service import ProviderCandidate, haversine_km
from app.services.security import hash_password
from app.tools.db_write_tool import (
    DbWriteError,
    _validate_transition,
    update_incident_status,
)
from app.tools.routing_tool import (
    FALLBACK_AVG_SPEED_KMH,
    ROAD_FACTOR,
    RouteResult,
    _route_via_fallback,
    get_route,
)


# ============================================================
# Section 1 — Haversine (pure)
# ============================================================


def test_haversine_zero_distance():
    assert haversine_km(40.0, -74.0, 40.0, -74.0) == 0.0


def test_haversine_known_distance_sf_to_nyc():
    # SF (37.7749, -122.4194) -> NYC (40.7128, -74.0060) ≈ 4129 km
    d = haversine_km(37.7749, -122.4194, 40.7128, -74.0060)
    assert 4100 < d < 4150, f"expected ~4129 km, got {d}"


def test_haversine_symmetric():
    a = haversine_km(33.6844, 73.0479, 31.5497, 74.3436)  # Islamabad -> Lahore
    b = haversine_km(31.5497, 74.3436, 33.6844, 73.0479)
    assert abs(a - b) < 0.001


# ============================================================
# Section 2 — Routing fallback (pure)
# ============================================================


def test_routing_fallback_computes_road_distance():
    r = _route_via_fallback(37.7749, -122.4194, 37.7849, -122.4094)
    straight = haversine_km(37.7749, -122.4194, 37.7849, -122.4094)
    assert r.source == "haversine_fallback"
    assert r.distance_km == pytest.approx(straight * ROAD_FACTOR, rel=1e-6)
    expected_minutes = (straight * ROAD_FACTOR / FALLBACK_AVG_SPEED_KMH) * 60.0
    assert r.duration_minutes == pytest.approx(expected_minutes, rel=1e-6)
    assert r.polyline is None


@pytest.mark.asyncio
async def test_get_route_uses_fallback_without_ors_key():
    from app.tools import routing_tool

    with patch.object(routing_tool.settings, "ORS_API_KEY", ""):
        result = await get_route(37.7749, -122.4194, 37.7849, -122.4094)
        assert result.source == "haversine_fallback"
        assert result.distance_km > 0


# ============================================================
# Section 3 — State machine validation (pure)
# ============================================================


def test_transition_reported_to_analyzing_allowed():
    _validate_transition("REPORTED", "ANALYZING")  # no raise


def test_transition_reported_to_arrived_blocked():
    with pytest.raises(DbWriteError, match="invalid status transition"):
        _validate_transition("REPORTED", "ARRIVED")


def test_transition_idempotent_same_status():
    _validate_transition("ASSIGNED", "ASSIGNED")  # no raise


def test_transition_from_closed_blocked():
    """CLOSED is terminal — no transitions allowed."""
    with pytest.raises(DbWriteError):
        _validate_transition("CLOSED", "EN_ROUTE")


def test_transition_assigned_to_en_route_allowed():
    _validate_transition("ASSIGNED", "EN_ROUTE")


def test_transition_en_route_to_arrived_allowed():
    _validate_transition("EN_ROUTE", "ARRIVED")


def test_transition_arrived_to_completed_allowed():
    _validate_transition("ARRIVED", "COMPLETED")


def test_transition_any_to_escalated_allowed():
    """ESCALATED can be reached from many states."""
    for src in ["ANALYZING", "ASSIGNED", "EN_ROUTE", "ARRIVED"]:
        _validate_transition(src, "ESCALATED")


# ============================================================
# Section 4 — DispatchAgent ranking logic (mocked Claude, no DB)
# ============================================================


def _candidate(*, name, distance_km, service_type="mechanic", total_jobs=0) -> ProviderCandidate:
    return ProviderCandidate(
        provider_id=uuid.uuid4(),
        name=name,
        phone=f"+1555{abs(hash(name)) % 10_000_000:07d}",
        service_type=service_type,
        distance_km=distance_km,
        is_available=True,
        is_approved=True,
        total_jobs=total_jobs,
    )


def test_heuristic_prefers_service_match_over_distance():
    """A farther exact-service provider beats a closer wrong-service provider."""
    candidates = [
        _candidate(name="Close Mechanic", distance_km=1.0, service_type="mechanic"),
        _candidate(name="Closer Tower", distance_km=0.5, service_type="tow_truck"),
    ]
    pick = DispatchAgent._heuristic_pick(candidates, desired_service="mechanic")
    assert pick.name == "Close Mechanic"


def test_heuristic_picks_closest_when_no_service_match():
    """If none match the desired service, closest wins."""
    candidates = [
        _candidate(name="Far", distance_km=10.0, service_type="tow_truck"),
        _candidate(name="Closer", distance_km=2.0, service_type="battery"),
    ]
    pick = DispatchAgent._heuristic_pick(candidates, desired_service="mechanic")
    assert pick.name == "Closer"


def test_heuristic_tiebreaks_on_total_jobs():
    """Same service and distance → more experienced provider wins."""
    a = _candidate(name="Novice", distance_km=5.0, service_type="mechanic", total_jobs=2)
    b = _candidate(name="Veteran", distance_km=5.0, service_type="mechanic", total_jobs=50)
    pick = DispatchAgent._heuristic_pick([a, b], desired_service="mechanic")
    assert pick.name == "Veteran"


def test_parse_ranking_valid_uuid_in_candidates():
    candidates = [_candidate(name="A", distance_km=1.0), _candidate(name="B", distance_km=2.0)]
    raw = json.dumps({
        "chosen_provider_id": str(candidates[1].provider_id),
        "reasoning": "B is more experienced",
    })
    chosen, reasoning = DispatchAgent._parse_ranking(raw, candidates)
    assert chosen is not None
    assert chosen.name == "B"
    assert "experienced" in reasoning


def test_parse_ranking_null_choice_returns_none():
    candidates = [_candidate(name="A", distance_km=1.0)]
    raw = json.dumps({"chosen_provider_id": None, "reasoning": "all unsuitable"})
    chosen, reasoning = DispatchAgent._parse_ranking(raw, candidates)
    assert chosen is None
    assert "unsuitable" in reasoning


def test_parse_ranking_unknown_uuid_returns_none():
    candidates = [_candidate(name="A", distance_km=1.0)]
    raw = json.dumps({
        "chosen_provider_id": "00000000-0000-0000-0000-000000000000",
        "reasoning": "x",
    })
    chosen, _ = DispatchAgent._parse_ranking(raw, candidates)
    assert chosen is None


@pytest.mark.parametrize("bad", [
    "not json",
    "[1, 2, 3]",
    '{"reasoning": "missing field"}',
    '{"chosen_provider_id": "not-a-uuid"}',
])
def test_parse_ranking_malformed_returns_none(bad):
    candidates = [_candidate(name="A", distance_km=1.0)]
    chosen, _ = DispatchAgent._parse_ranking(bad, candidates)
    assert chosen is None


# ============================================================
# Section 5 — DispatchAgent end-to-end (mocked Claude, real DB)
# ============================================================


async def _make_provider(db_session, *, lat, lng, service_type, name, phone):
    from app.models.provider import Provider
    from app.models.user import User
    user = User(
        phone=phone, name=name, role=UserRole.provider.value,
        password_hash=hash_password("password123"),
        is_active=True, is_phone_verified=True,
    )
    db_session.add(user)
    await db_session.flush()
    provider = Provider(
        id=user.id, service_type=service_type,
        is_available=True, is_approved=True, total_jobs=0,
        location=f"SRID=4326;POINT({lng} {lat})",
    )
    db_session.add(provider)
    await db_session.flush()
    return user, provider


async def _make_incident(db_session, *, lat, lng, customer_id) -> Incident:
    incident = Incident(
        customer_id=customer_id, lat=lat, lng=lng,
        description="test incident",
        status=IncidentStatus.ANALYZING.value,
    )
    db_session.add(incident)
    await db_session.flush()
    return incident


async def _make_customer(db_session, phone="+15558881111"):
    from app.models.user import User
    user = User(
        phone=phone, name="Customer", role=UserRole.customer.value,
        password_hash=hash_password("password123"),
        is_active=True, is_phone_verified=True,
    )
    db_session.add(user)
    await db_session.flush()
    return user


@pytest.mark.asyncio
async def test_dispatch_assigns_only_candidate(db_session):
    """Single available provider in radius → gets assigned, no Claude call needed."""
    customer = await _make_customer(db_session, "+15558880001")
    _, _ = await _make_provider(
        db_session, lat=37.7749, lng=-122.4194,
        service_type="mechanic", name="Solo Mechanic", phone="+15558880002",
    )
    incident = await _make_incident(
        db_session, lat=37.7749, lng=-122.4194, customer_id=customer.id,
    )

    # Claude must NOT be called — provider count is 1.
    client = MagicMock()
    client.messages = MagicMock()
    client.messages.create = AsyncMock(
        side_effect=AssertionError("Claude must not be called when there's only one candidate")
    )

    agent = DispatchAgent(anthropic_client=client)
    ctx = AgentContext(
        db=db_session,
        incident_id=incident.id,
        payload={"lat": 37.7749, "lng": -122.4194, "service_type": "mechanic"},
    )
    result = await agent.run(ctx)
    assert result.success
    assert result.output.assigned is True
    assert result.output.provider_name == "Solo Mechanic"
    # incident must be in ASSIGNED state
    await db_session.refresh(incident)
    assert incident.status == IncidentStatus.ASSIGNED.value
    assert incident.provider_id is not None
    assert incident.eta_minutes is not None


@pytest.mark.asyncio
async def test_dispatch_expands_radius_when_initial_empty(db_session):
    """No providers at 50 km but one at 75 km → expansion succeeds."""
    customer = await _make_customer(db_session, "+15558880011")
    # Put the only provider ~75 km north of incident (in San Francisco direction)
    far_lat = 37.7749 + (75 / 111.0)
    _, _ = await _make_provider(
        db_session, lat=far_lat, lng=-122.4194,
        service_type="mechanic", name="Far Mechanic", phone="+15558880012",
    )
    incident = await _make_incident(
        db_session, lat=37.7749, lng=-122.4194, customer_id=customer.id,
    )

    client = MagicMock()
    client.messages = MagicMock()
    client.messages.create = AsyncMock()  # not called for single candidate

    agent = DispatchAgent(anthropic_client=client)
    ctx = AgentContext(
        db=db_session, incident_id=incident.id,
        payload={"lat": 37.7749, "lng": -122.4194, "service_type": None},
    )
    result = await agent.run(ctx)
    assert result.success
    assert result.output.assigned is True
    assert result.output.radius_used_km == 100.0  # MAX_RADIUS expansion fired


@pytest.mark.asyncio
async def test_dispatch_no_provider_returns_unassigned(db_session):
    """Nobody anywhere → returns assigned=False, status not changed to ASSIGNED."""
    customer = await _make_customer(db_session, "+15558880021")
    incident = await _make_incident(
        db_session, lat=37.7749, lng=-122.4194, customer_id=customer.id,
    )
    agent = DispatchAgent(anthropic_client=MagicMock())
    ctx = AgentContext(
        db=db_session, incident_id=incident.id,
        payload={"lat": 37.7749, "lng": -122.4194, "service_type": "mechanic"},
    )
    result = await agent.run(ctx)
    assert result.success  # run() succeeded; the dispatch decision was negative
    assert result.output.assigned is False
    assert result.output.candidates_considered == 0
    await db_session.refresh(incident)
    assert incident.status == IncidentStatus.ANALYZING.value  # unchanged


@pytest.mark.asyncio
async def test_dispatch_uses_claude_ranking_with_multiple_candidates(db_session):
    """Multiple candidates → Claude ranking decides who is chosen."""
    customer = await _make_customer(db_session, "+15558880031")
    _, prov_a = await _make_provider(
        db_session, lat=37.7749, lng=-122.4194,
        service_type="mechanic", name="Near Mechanic", phone="+15558880032",
    )
    user_b, _ = await _make_provider(
        db_session, lat=37.7849, lng=-122.4094,
        service_type="mechanic", name="Veteran Mechanic", phone="+15558880033",
    )
    # Mark veteran with more jobs so the ranking explanation is sensible
    veteran_profile = await db_session.get(__import__(
        "app.models.provider", fromlist=["Provider"]).Provider, user_b.id)
    veteran_profile.total_jobs = 50
    await db_session.flush()

    incident = await _make_incident(
        db_session, lat=37.7749, lng=-122.4194, customer_id=customer.id,
    )

    # Claude picks the veteran by uuid
    response = MagicMock()
    block = MagicMock()
    block.type = "text"
    block.text = json.dumps({
        "chosen_provider_id": str(user_b.id),
        "reasoning": "Veteran has more experience and is still close.",
    })
    response.content = [block]
    client = MagicMock()
    client.messages = MagicMock()
    client.messages.create = AsyncMock(return_value=response)

    agent = DispatchAgent(anthropic_client=client)
    ctx = AgentContext(
        db=db_session, incident_id=incident.id,
        payload={"lat": 37.7749, "lng": -122.4194, "service_type": "mechanic"},
    )
    result = await agent.run(ctx)
    assert result.success
    assert result.output.assigned is True
    assert result.output.provider_name == "Veteran Mechanic"
    assert "veteran" in result.output.reasoning.lower() or "experience" in result.output.reasoning.lower()


@pytest.mark.asyncio
async def test_dispatch_falls_back_to_heuristic_when_claude_fails(db_session):
    """If Claude errors during ranking, the heuristic picker still produces a choice."""
    customer = await _make_customer(db_session, "+15558880041")
    await _make_provider(
        db_session, lat=37.7749, lng=-122.4194,
        service_type="mechanic", name="A", phone="+15558880042",
    )
    await _make_provider(
        db_session, lat=37.7849, lng=-122.4094,
        service_type="mechanic", name="B", phone="+15558880043",
    )
    incident = await _make_incident(
        db_session, lat=37.7749, lng=-122.4194, customer_id=customer.id,
    )

    client = MagicMock()
    client.messages = MagicMock()
    client.messages.create = AsyncMock(side_effect=RuntimeError("network down"))

    agent = DispatchAgent(anthropic_client=client)
    ctx = AgentContext(
        db=db_session, incident_id=incident.id,
        payload={"lat": 37.7749, "lng": -122.4194, "service_type": "mechanic"},
    )
    result = await agent.run(ctx)
    assert result.success
    assert result.output.assigned is True
    assert "Heuristic pick" in result.output.reasoning

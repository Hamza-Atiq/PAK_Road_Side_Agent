"""Tests for AdminAgent — intent parser (pure) + handler integration."""
from __future__ import annotations

import json
import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.agents.admin_agent import (
    ALLOWED_INTENTS,
    AdminAgent,
    _deterministic_summary,
    _parse_intent,
    build_dashboard_payload,
)
from app.agents.base import AgentContext, AgentResult
from app.agents.communication import CommunicationResult
from app.agents.dispatch import DispatchResult
from app.models.enums import IncidentStatus, UserRole
from app.models.incident import Incident
from app.services.security import hash_password


# ============================================================
# Section 1 — Intent parser (pure)
# ============================================================


def test_parser_accepts_all_known_intents():
    """Every value listed in ALLOWED_INTENTS must parse back cleanly."""
    for intent in ALLOWED_INTENTS:
        raw = json.dumps({"intent": intent, "params": {}})
        got_intent, got_params = _parse_intent(raw)
        assert got_intent == intent
        assert got_params == {}


def test_parser_strips_code_fences():
    raw = '```json\n{"intent": "query_metrics", "params": {}}\n```'
    intent, params = _parse_intent(raw)
    assert intent == "query_metrics"


@pytest.mark.parametrize("bad", [
    "",
    "not json",
    "[1, 2]",
    '{"params": {}}',                     # missing intent
    '{"intent": "drop_database"}',        # not in allow-list
    '{"intent": "query_incidents", "params": "no"}',  # params not a dict
])
def test_parser_rejects_invalid_input(bad):
    intent, params = _parse_intent(bad)
    assert intent == "unknown"
    assert params == {}


def test_parser_returns_params_dict():
    raw = json.dumps({
        "intent": "query_incidents",
        "params": {"status_in": ["ASSIGNED"], "since_hours": 6},
    })
    intent, params = _parse_intent(raw)
    assert intent == "query_incidents"
    assert params["status_in"] == ["ASSIGNED"]
    assert params["since_hours"] == 6


# ============================================================
# Section 2 — Deterministic summary fallback (pure)
# ============================================================


def test_summary_query_incidents():
    s = _deterministic_summary("query_incidents", {"count": 7})
    assert "7" in s


def test_summary_reassign_success_vs_failure():
    ok = _deterministic_summary("reassign_incident", {
        "reassigned": True, "new_provider_name": "Tom",
    })
    assert "Tom" in ok
    fail = _deterministic_summary("reassign_incident", {
        "reassigned": False, "reason": "no provider",
    })
    assert "failed" in fail.lower() or "no provider" in fail.lower()


def test_summary_unknown_intent():
    s = _deterministic_summary("unknown", {})
    assert "not recognized" in s.lower()


# ============================================================
# Helpers for DB tests
# ============================================================


def _mock_claude(text: str) -> MagicMock:
    block = MagicMock()
    block.type = "text"
    block.text = text
    response = MagicMock()
    response.content = [block]
    client = MagicMock()
    client.messages = MagicMock()
    client.messages.create = AsyncMock(return_value=response)
    return client


async def _make_admin(db_session, phone="+15556660099"):
    from app.models.user import User
    u = User(
        phone=phone, name="Admin", role=UserRole.admin.value,
        password_hash=hash_password("password123"),
        is_active=True, is_phone_verified=True,
    )
    db_session.add(u)
    await db_session.flush()
    return u


async def _make_customer(db_session, phone="+15556660001"):
    from app.models.user import User
    u = User(
        phone=phone, name="Customer", role=UserRole.customer.value,
        password_hash=hash_password("password123"),
        is_active=True, is_phone_verified=True,
    )
    db_session.add(u)
    await db_session.flush()
    return u


async def _make_provider(db_session, *, phone, name, service_type="mechanic",
                         is_available=True, is_approved=True):
    from app.models.provider import Provider
    from app.models.user import User
    u = User(
        phone=phone, name=name, role=UserRole.provider.value,
        password_hash=hash_password("password123"),
        is_active=True, is_phone_verified=True,
    )
    db_session.add(u)
    await db_session.flush()
    p = Provider(
        id=u.id, service_type=service_type,
        is_available=is_available, is_approved=is_approved,
        total_jobs=3, location="SRID=4326;POINT(-122.4194 37.7749)",
    )
    db_session.add(p)
    await db_session.flush()
    return u, p


async def _make_incident(db_session, *, customer_id, status=IncidentStatus.ANALYZING,
                         provider_id=None):
    inc = Incident(
        customer_id=customer_id, provider_id=provider_id,
        lat=37.7749, lng=-122.4194,
        description="test", status=status.value,
    )
    db_session.add(inc)
    await db_session.flush()
    return inc


# ============================================================
# Section 3 — Dashboard aggregator (real DB)
# ============================================================


@pytest.mark.asyncio
async def test_dashboard_payload_aggregates_correctly(db_session):
    await _make_admin(db_session, "+15556661099")
    customer = await _make_customer(db_session, "+15556661001")
    prov_user, _ = await _make_provider(db_session, phone="+15556661002", name="Tom")

    # 2 ASSIGNED, 1 COMPLETED, 1 NO_PROVIDER
    for _ in range(2):
        await _make_incident(
            db_session, customer_id=customer.id, status=IncidentStatus.ASSIGNED,
            provider_id=prov_user.id,
        )
    await _make_incident(
        db_session, customer_id=customer.id, status=IncidentStatus.COMPLETED,
    )
    await _make_incident(
        db_session, customer_id=customer.id, status=IncidentStatus.NO_PROVIDER,
    )

    payload = await build_dashboard_payload(db_session)
    assert payload["incidents_by_status"]["ASSIGNED"] == 2
    assert payload["incidents_by_status"]["COMPLETED"] == 1
    assert payload["incidents_by_status"]["NO_PROVIDER"] == 1
    # Open count = REPORTED + ANALYZING + ASSIGNED + EN_ROUTE + ARRIVED + NO_PROVIDER
    assert payload["open_incidents_count"] >= 3
    assert payload["providers"]["total_approved"] >= 1
    assert payload["providers"]["available_now"] >= 1


# ============================================================
# Section 4 — Intent handlers (real DB, mocked Claude where needed)
# ============================================================


@pytest.mark.asyncio
async def test_query_incidents_handler_filters_by_status(db_session):
    customer = await _make_customer(db_session, "+15556662001")
    await _make_incident(db_session, customer_id=customer.id, status=IncidentStatus.ASSIGNED)
    await _make_incident(db_session, customer_id=customer.id, status=IncidentStatus.COMPLETED)
    result = await AdminAgent._query_incidents(
        db_session, {"status_in": ["ASSIGNED"]}
    )
    assert result["count"] == 1
    assert all(i["status"] == "ASSIGNED" for i in result["incidents"])


@pytest.mark.asyncio
async def test_query_providers_handler_filters_by_availability(db_session):
    await _make_provider(db_session, phone="+15556663001", name="A", is_available=True)
    await _make_provider(db_session, phone="+15556663002", name="B", is_available=False)
    avail = await AdminAgent._query_providers(db_session, {"is_available": True})
    assert avail["count"] >= 1
    assert all(p["is_available"] for p in avail["providers"])


@pytest.mark.asyncio
async def test_suspend_provider_handler(db_session):
    user, provider = await _make_provider(
        db_session, phone="+15556664001", name="Suspendable",
    )
    agent = AdminAgent(anthropic_client=MagicMock())
    result = await agent._suspend_provider(
        db_session, {"provider_id": str(user.id), "reason": "test"},
    )
    assert result["suspended"] is True
    await db_session.refresh(user)
    await db_session.refresh(provider)
    assert user.is_active is False
    assert provider.is_available is False


@pytest.mark.asyncio
async def test_suspend_provider_handler_rejects_unknown_id(db_session):
    agent = AdminAgent(anthropic_client=MagicMock())
    result = await agent._suspend_provider(
        db_session, {"provider_id": str(uuid.uuid4())},
    )
    assert "error" in result


@pytest.mark.asyncio
async def test_notify_user_handler_sends_via_communication(db_session):
    agent = AdminAgent(anthropic_client=MagicMock())
    # Stub communication so we don't actually call Twilio
    stub_msg_id = uuid.uuid4()
    stub_result = CommunicationResult(
        sent=True, message_id=stub_msg_id, channel="sms",
        twilio_sid="SM_admin_test", content="hello", reason="ok",
    )
    agent.communication.run = AsyncMock(return_value=AgentResult(
        success=True, output=stub_result, agent_name="CommunicationAgent",
    ))

    ctx = AgentContext(db=db_session)
    result = await agent._notify_user(
        ctx, {"to_phone": "+15555550001", "body": "test admin notification"},
    )
    assert result["sent"] is True
    assert result["message_id"] == str(stub_msg_id)


@pytest.mark.asyncio
async def test_notify_user_handler_requires_phone_and_body(db_session):
    agent = AdminAgent(anthropic_client=MagicMock())
    ctx = AgentContext(db=db_session)
    out = await agent._notify_user(ctx, {})
    assert "error" in out
    out = await agent._notify_user(ctx, {"to_phone": "+15555550002"})
    assert "error" in out


# ============================================================
# Section 5 — Top-level _execute orchestration (mocked Claude)
# ============================================================


@pytest.mark.asyncio
async def test_admin_agent_routes_to_query_metrics_intent(db_session):
    # Claude returns: classifier picks query_metrics, then summarizer writes a one-liner
    classifier_response = json.dumps({"intent": "query_metrics", "params": {}})
    summary_response = "All quiet — 0 open incidents."

    client = MagicMock()
    client.messages = MagicMock()
    create_mock = AsyncMock()
    create_mock.side_effect = [
        MagicMock(content=[MagicMock(type="text", text=classifier_response)]),
        MagicMock(content=[MagicMock(type="text", text=summary_response)]),
    ]
    client.messages.create = create_mock

    agent = AdminAgent(anthropic_client=client)
    ctx = AgentContext(db=db_session, payload={"query": "How's the system looking?"})
    result = await agent.run(ctx)
    assert result.success, result.error
    out = result.output
    assert out.intent == "query_metrics"
    assert "open" in out.summary.lower() or "quiet" in out.summary.lower()
    assert out.actioned is False
    assert "incidents_by_status" in out.data


@pytest.mark.asyncio
async def test_admin_agent_unknown_intent_does_not_error(db_session):
    classifier_response = json.dumps({"intent": "unknown", "params": {}})
    client = MagicMock()
    client.messages = MagicMock()
    client.messages.create = AsyncMock(return_value=MagicMock(
        content=[MagicMock(type="text", text=classifier_response)],
    ))
    agent = AdminAgent(anthropic_client=client)
    ctx = AgentContext(db=db_session, payload={"query": "What's the weather in Mars?"})
    result = await agent.run(ctx)
    assert result.success
    assert result.output.intent == "unknown"
    assert result.output.actioned is False


@pytest.mark.asyncio
async def test_admin_agent_validates_query_payload(db_session):
    agent = AdminAgent(anthropic_client=MagicMock())
    ctx = AgentContext(db=db_session, payload={"query": ""})
    result = await agent.run(ctx)
    assert result.success is False
    assert "query" in result.error.lower()


@pytest.mark.asyncio
async def test_admin_agent_tool_allow_list():
    """AdminAgent has read + write + comm tools, but NOT vision/transcription/routing."""
    agent = AdminAgent(anthropic_client=MagicMock())
    assert "db_read_tool" in agent.tools
    assert "db_write_tool" in agent.tools
    assert "twilio_tool" in agent.tools
    from app.agents.base import ToolNotAuthorizedError
    for forbidden in ("vision_tool", "transcription_tool", "routing_tool", "geo_tool"):
        with pytest.raises(ToolNotAuthorizedError):
            agent._check_tool_authorized(forbidden)

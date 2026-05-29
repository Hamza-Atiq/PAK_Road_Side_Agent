"""Demo Scenario 8 — Admin override via natural-language query.

Two parts shown in this single scenario:

Part A — Admin types a free-form notify request:
  "send an SMS to +15551111008 saying their replacement provider is on the way"
AdminAgent classifies intent=notify_user, params={to_phone, body} and dispatches
CommunicationAgent which calls Twilio.

Part B — Admin requests a reassign:
  "reassign incident <id>"
AdminAgent classifies intent=reassign_incident, releases the old provider,
runs DispatchAgent again, returns the new assignment.

Together they validate the AdminAgent's classifier + safe-handler dispatch.
"""
from __future__ import annotations

import json

import pytest

from app.agents.admin_agent import AdminAgent
from app.agents.base import AgentContext
from app.models.enums import IncidentStatus

from tests.demo.conftest import (
    fake_anthropic_router,
    seed_admin,
    seed_customer,
    seed_incident,
    seed_provider,
)


# ============================================================
# Part A — notify_user
# ============================================================


@pytest.mark.asyncio
async def test_scenario_8a_admin_notify(db_session, bus, capsys):
    admin = await seed_admin(db_session, phone="+15550000088")
    customer = await seed_customer(db_session, phone="+15551111088")

    query = (
        f"send an SMS to {customer.phone} saying "
        "'your replacement provider is on the way'"
    )

    intent_payload = json.dumps({
        "intent": "notify_user",
        "params": {
            "to_phone": customer.phone,
            "body": "Your replacement provider is on the way",
        },
    })

    client = fake_anthropic_router({
        "admin-query classifier": intent_payload,
        "summarize structured query results":
            "Message queued to the customer.",
        "roadside-assistance platform":
            "Your replacement provider is on the way",
    })

    agent = AdminAgent(anthropic_client=client)
    ctx = AgentContext(db=db_session, user_id=admin.id, payload={"query": query})
    result = await agent.run(ctx)
    assert result.success, result.error
    outcome = result.output

    assert outcome.intent == "notify_user"
    assert outcome.actioned is True

    cust_msgs = [m for m in bus.sent_messages if m.to_phone == customer.phone]
    assert cust_msgs, "customer must receive the admin-issued SMS"

    print("\n=== Scenario 8a: Admin natural-language notify ===")
    print(f"Admin query: {query}")
    print(f"Intent classified: {outcome.intent}")
    print(f"Customer message: {cust_msgs[0].content[:80]}")


# ============================================================
# Part B — reassign_incident
# ============================================================


@pytest.mark.asyncio
async def test_scenario_8b_admin_reassign(db_session, bus, capsys):
    admin = await seed_admin(db_session, phone="+15550000089")
    customer = await seed_customer(db_session, phone="+15551111089")

    # Place Original Tom far away so the admin reassign cannot pick him again
    # even after his availability flag is released by the handler.
    original_user, _ = await seed_provider(
        db_session, phone="+15552222088", name="Original Tom",
        lat=40.7128, lng=-74.0060,  # New York — far outside SF dispatch radius
        service_type="mechanic",
        is_available=False,
    )
    target_user, _ = await seed_provider(
        db_session, phone="+15552222089", name="Sarah Replacement",
        lat=37.7749, lng=-122.4194, service_type="mechanic",
        is_available=True,
    )

    incident = await seed_incident(db_session, customer_id=customer.id,
                                   description="dead battery")
    incident.provider_id = original_user.id
    incident.status = IncidentStatus.ASSIGNED.value
    await db_session.flush()

    query = f"reassign incident {incident.id} to another available provider"

    intent_payload = json.dumps({
        "intent": "reassign_incident",
        "params": {"incident_id": str(incident.id)},
    })

    client = fake_anthropic_router({
        "admin-query classifier": intent_payload,
        "summarize structured query results":
            f"Incident reassigned from Original Tom to {target_user.name}.",
    })

    agent = AdminAgent(anthropic_client=client)
    ctx = AgentContext(db=db_session, user_id=admin.id, payload={"query": query})
    result = await agent.run(ctx)
    assert result.success, result.error
    outcome = result.output

    assert outcome.intent == "reassign_incident"
    assert outcome.actioned is True
    assert outcome.data.get("reassigned") is True
    assert outcome.data.get("new_provider_id") == str(target_user.id)

    await db_session.refresh(incident)
    assert incident.provider_id == target_user.id

    print("\n=== Scenario 8b: Admin override — reassign ===")
    print(f"Admin query: {query}")
    print(f"Old provider: {original_user.name} -> new: {target_user.name}")
    print(f"Summary: {outcome.summary[:120]}")

"""Demo Scenario 6 — Provider goes offline mid-job → auto re-dispatch.

A provider was assigned but stopped sending GPS pings. TrackingAgent detects
this on its 60-second sweep and spawns EscalationAgent with PROVIDER_OFFLINE.
The escalation handler releases the absent provider, clears the link, runs
DispatchAgent again, finds a replacement, and notifies the customer.

Expected timeline
-----------------
ASSIGNED → (provider offline) → EscalationAgent(PROVIDER_OFFLINE)
  → release old provider + clear link
  → DispatchAgent run #2 → new provider found
  → customer notified with "reassigned" message.
"""
from __future__ import annotations

import json

import pytest

from app.agents.base import AgentContext
from app.agents.escalation import EscalationAgent, EscalationReason
from app.models.enums import IncidentStatus

from tests.demo.conftest import (
    fake_anthropic_router,
    seed_customer,
    seed_incident,
    seed_provider,
)


@pytest.mark.asyncio
async def test_scenario_6_provider_offline_redispatch(db_session, bus, capsys):
    customer = await seed_customer(db_session, phone="+15551111006")

    # Two providers. The escalation handler releases the old provider's
    # availability flag, so to keep him out of the new candidate set we place
    # him well outside the 50 km PostGIS search radius. Sarah sits right at
    # the incident location and is unambiguously the right pick.
    old_user, old_prov = await seed_provider(
        db_session, phone="+15552222060", name="Original Tom",
        lat=40.7128, lng=-74.0060,  # New York — far from the SF incident
        service_type="mechanic",
        is_available=False,
    )
    new_user, new_prov = await seed_provider(
        db_session, phone="+15552222061", name="Replacement Sarah",
        lat=37.7749, lng=-122.4194, service_type="mechanic",
        is_available=True,
    )

    incident = await seed_incident(
        db_session, customer_id=customer.id,
        description="Dead battery, parked downtown",
    )
    incident.provider_id = old_user.id
    incident.status = IncidentStatus.ASSIGNED.value
    incident.ai_diagnosis = {"service_needed": "mechanic", "issue_type": "dead battery"}
    await db_session.flush()

    client = fake_anthropic_router({
        "roadside-assistance platform":
            "Update — your previous provider couldn't make it. Replacement Sarah is on the way (~10 min).",
    })

    agent = EscalationAgent(anthropic_client=client)
    ctx = AgentContext(
        db=db_session, incident_id=incident.id,
        payload={"reason": EscalationReason.PROVIDER_OFFLINE.value},
    )
    result = await agent.run(ctx)
    assert result.success, result.error
    outcome = result.output

    assert outcome.redispatched is True
    assert outcome.new_provider_id == new_user.id

    await db_session.refresh(incident)
    assert incident.status == IncidentStatus.ASSIGNED.value
    assert incident.provider_id == new_user.id

    # Customer should have received a reassignment SMS
    cust_msgs = [m for m in bus.sent_messages if m.to_phone == customer.phone]
    assert cust_msgs, "customer must be told about the reassignment"

    print("\n=== Scenario 6: Provider offline → auto-redispatch ===")
    print(f"Original provider: {old_user.name} (released)")
    print(f"New provider: {new_user.name}")
    print(f"Customer notified: {cust_msgs[0].content[:80]}")

"""Demo Scenario 4 — No provider available.

Customer reports a breakdown but no providers are seeded within the maximum
dispatch radius. DispatchAgent expands radius and still finds nothing.
Orchestrator transitions incident to NO_PROVIDER and alerts the admin.

Expected timeline
-----------------
REPORTED → ANALYZING → NO_PROVIDER + admin SMS alert
"""
from __future__ import annotations

import json

import pytest

from app.agents.base import AgentContext
from app.agents.orchestrator import OrchestratorAgent
from app.models.enums import IncidentStatus

from tests.demo.conftest import (
    fake_anthropic_router,
    seed_admin,
    seed_customer,
    seed_incident,
)


@pytest.mark.asyncio
async def test_scenario_4_no_provider(db_session, bus, capsys):
    customer = await seed_customer(db_session, phone="+15551111004")
    admin = await seed_admin(db_session, phone="+15550000004")
    # No providers seeded
    incident = await seed_incident(
        db_session, customer_id=customer.id,
        description="Engine seized up; need a tow truck.",
        # Way out in the middle of nowhere
        lat=10.0, lng=10.0,
    )

    client = fake_anthropic_router({
        "strict security classifier": json.dumps({
            "safe": True, "reason": "ok", "sanitized": "Engine seized up; need tow.",
            "patterns": [],
        }),
        "vehicle diagnostician": json.dumps({
            "issue_type": "engine seized",
            "severity": "high",
            "service_needed": "tow_truck",
            "confidence": 0.9,
        }),
        "roadside-assistance platform":
            "URGENT: no providers available within range for incident at 10.0,10.0",
    })

    orch = OrchestratorAgent(anthropic_client=client)
    result = await orch.run(AgentContext(db=db_session, incident_id=incident.id))
    assert result.success
    outcome = result.output

    assert outcome.dispatch.assigned is False
    assert outcome.admin_alerted is True

    await db_session.refresh(incident)
    assert incident.status == IncidentStatus.NO_PROVIDER.value

    # The admin should be the recipient of an alert SMS
    admin_msgs = [m for m in bus.sent_messages if m.to_phone == admin.phone]
    assert admin_msgs, "admin must receive a NO_PROVIDER alert"

    print("\n=== Scenario 4: No provider available ===")
    print(f"Final status: {incident.status}")
    print(f"Search radius used: {outcome.dispatch.radius_used_km} km")
    print(f"Admin alerted on phone {admin.phone}: {admin_msgs[0].content[:80]}")

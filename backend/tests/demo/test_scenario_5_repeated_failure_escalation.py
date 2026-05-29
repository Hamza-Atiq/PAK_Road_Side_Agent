"""Demo Scenario 5 — Repeated failure triggers EscalationAgent.

An incident has cycled through two failed dispatches already. The TrackingAgent
flagged it as REPEATED_FAILURE and spawns EscalationAgent. The escalation
handler marks the incident ESCALATED (terminal, awaiting human action) and
alerts an admin with a summary.

Expected timeline
-----------------
ANALYZING (failed twice) → EscalationAgent(REPEATED_FAILURE) → ESCALATED + admin alert.
"""
from __future__ import annotations

import pytest

from app.agents.base import AgentContext
from app.agents.escalation import EscalationAgent, EscalationReason
from app.models.enums import IncidentStatus

from tests.demo.conftest import (
    fake_anthropic_router,
    seed_admin,
    seed_customer,
    seed_incident,
)


@pytest.mark.asyncio
async def test_scenario_5_repeated_failure_escalates(db_session, bus, capsys):
    customer = await seed_customer(db_session, phone="+15551111005")
    admin = await seed_admin(db_session, phone="+15550000005")
    incident = await seed_incident(
        db_session, customer_id=customer.id,
        description="Battery dead for the 3rd time — previous providers cancelled",
    )
    # Simulate the prior failures by bumping retry_count past the threshold
    incident.retry_count = 3
    incident.status = IncidentStatus.ANALYZING.value
    await db_session.flush()

    # EscalationAgent uses CommunicationAgent for admin alerts (Claude-driven text)
    client = fake_anthropic_router({
        "roadside-assistance platform":
            "URGENT: incident escalated after 3 failed dispatch attempts; manual handling required.",
    })

    agent = EscalationAgent(anthropic_client=client)
    ctx = AgentContext(
        db=db_session,
        incident_id=incident.id,
        payload={"reason": EscalationReason.REPEATED_FAILURE.value},
    )
    result = await agent.run(ctx)
    assert result.success, result.error
    outcome = result.output

    assert outcome.reason == EscalationReason.REPEATED_FAILURE.value
    assert outcome.admin_alerted is True

    await db_session.refresh(incident)
    assert incident.status == IncidentStatus.ESCALATED.value

    admin_msgs = [m for m in bus.sent_messages if m.to_phone == admin.phone]
    assert admin_msgs, "admin must receive an escalation alert"

    print("\n=== Scenario 5: Repeated failure → escalation ===")
    print(f"Final status: {incident.status}")
    print(f"Retry count when escalated: {incident.retry_count}")
    print(f"Admin alerted: {admin_msgs[0].content[:80]}")

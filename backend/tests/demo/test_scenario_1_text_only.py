"""Demo Scenario 1 — Text-only breakdown report (happy path).

Setup
-----
- Customer Alice submits "engine won't start" via text only.
- Three providers seeded in SF; nearest is Tom Mechanic.
- Anthropic + Twilio stubbed.

Expected timeline
-----------------
REPORTED → ANALYZING → ASSIGNED → (customer + provider both notified)

What this proves to a judge
---------------------------
End-to-end agent pipeline runs from a single API submission, with no human
in the loop. GuardrailAgent clears the input, TriageAgent diagnoses, DispatchAgent
picks the closest match, CommunicationAgent writes two contextual messages.
"""
from __future__ import annotations

import json

import pytest

from app.agents.base import AgentContext
from app.agents.orchestrator import OrchestratorAgent
from app.models.enums import IncidentStatus

from tests.demo.conftest import (
    fake_anthropic_router,
    seed_customer,
    seed_incident,
    seed_provider,
)


@pytest.mark.asyncio
async def test_scenario_1_text_only(db_session, bus, capsys):
    # ----- Seed -----
    customer = await seed_customer(db_session, phone="+15551111001", name="Alice Driver")
    provider_user, _ = await seed_provider(
        db_session, phone="+15552222001", name="Tom Mechanic",
        lat=37.7749, lng=-122.4194, service_type="mechanic",
    )
    incident = await seed_incident(
        db_session, customer_id=customer.id,
        description="My engine won't start after I parked at the grocery store",
    )

    # ----- Wire stubbed Claude responses (one per agent) -----
    client = fake_anthropic_router({
        # Guardrail clears the input
        "strict security classifier": json.dumps({
            "safe": True, "reason": "ordinary vehicle complaint",
            "sanitized": "My engine won't start after I parked at the grocery store",
            "patterns": [],
        }),
        # Triage diagnoses
        "vehicle diagnostician": json.dumps({
            "issue_type": "battery or starter failure",
            "severity": "medium",
            "service_needed": "battery",
            "confidence": 0.85,
            "details": "Likely dead battery. Bring jump-starter and tester.",
        }),
        # Communication agent text (orchestrator skips ranking Claude — single candidate)
        "roadside-assistance platform": "Help on the way — Tom Mechanic arriving in about 8 minutes.",
    })

    # ----- Run -----
    orch = OrchestratorAgent(anthropic_client=client)
    result = await orch.run(AgentContext(db=db_session, incident_id=incident.id))

    # ----- Assertions -----
    assert result.success, result.error
    outcome = result.output
    assert outcome.guardrail_safe is True
    assert outcome.diagnosis.issue_type
    assert outcome.dispatch.assigned is True
    assert outcome.dispatch.provider_id == provider_user.id
    assert outcome.customer_notified is True
    assert outcome.provider_notified is True

    await db_session.refresh(incident)
    assert incident.status == IncidentStatus.ASSIGNED.value

    # ----- Demo output -----
    msgs = bus.sent_messages
    print("\n=== Scenario 1: Text-only happy path ===")
    print(f"Final status: {incident.status}")
    print(f"Diagnosis: {outcome.diagnosis.issue_type}")
    print(f"Provider: {outcome.dispatch.provider_name} ({outcome.dispatch.distance_km:.2f} km)")
    print(f"Messages sent: {len(msgs)}")
    for m in msgs:
        print(f"  [{m.channel}] -> {m.to_phone}: {m.content[:80]}")
    assert any(m.to_phone == customer.phone for m in msgs), "customer must be notified"
    assert any(m.to_phone == provider_user.phone for m in msgs), "provider must be notified"

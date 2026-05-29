"""Demo Scenario 3 — Voice note diagnosis.

Customer is hands-busy (smoke from the hood) and records a voice note instead
of typing. TriageAgent invokes transcription_tool → gets the transcript →
diagnoses overheating → dispatches the nearest available provider.

Expected timeline
-----------------
REPORTED → ANALYZING (transcription + text diagnosis) → ASSIGNED → notified.
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
async def test_scenario_3_voice(db_session, bus, monkeypatch, capsys):
    customer = await seed_customer(db_session, phone="+15551111003")
    prov_user, _ = await seed_provider(
        db_session, phone="+15552222020", name="Sarah TowTruck",
        lat=37.7749, lng=-122.4194, service_type="tow_truck",
    )

    incident = await seed_incident(
        db_session, customer_id=customer.id,
        description=None,
        voice_url="/uploads/demo_overheat.mp3",
    )

    # ----- Stub transcription -----
    # NB: triage imports `transcribe_voice_note` by name at module-load, so we
    # also patch the binding in `app.agents.triage`.
    from app.tools import transcription_tool
    from app.agents import triage as triage_mod

    async def _fake_transcribe(voice_url, *, anthropic_client=None):
        return "There's white smoke coming from under the hood and the temperature gauge is in the red zone."

    monkeypatch.setattr(transcription_tool, "transcribe_voice_note", _fake_transcribe)
    monkeypatch.setattr(triage_mod, "transcribe_voice_note", _fake_transcribe)

    # ----- Stub guardrail + triage text + communication -----
    client = fake_anthropic_router({
        "strict security classifier": json.dumps({
            "safe": True, "reason": "transcribed voice", "sanitized": "white smoke + temp redline",
            "patterns": [],
        }),
        "vehicle diagnostician": json.dumps({
            "issue_type": "engine overheating",
            "severity": "high",
            "service_needed": "tow_truck",
            "confidence": 0.9,
            "details": "Stop the car immediately. Tow recommended.",
        }),
        "roadside-assistance platform":
            "Help on the way — Sarah will be there in about 12 minutes with a tow truck.",
    })

    orch = OrchestratorAgent(anthropic_client=client)
    result = await orch.run(AgentContext(db=db_session, incident_id=incident.id))
    assert result.success
    outcome = result.output

    # DiagnosisResult uses use_enum_values=True; fields are plain strings.
    assert outcome.diagnosis.service_needed == "tow_truck"
    assert outcome.diagnosis.severity == "high"
    assert outcome.dispatch.assigned is True
    assert outcome.dispatch.provider_id == prov_user.id

    await db_session.refresh(incident)
    assert incident.status == IncidentStatus.ASSIGNED.value

    print("\n=== Scenario 3: Voice note ===")
    print(f"Diagnosis: {outcome.diagnosis.issue_type} ({outcome.diagnosis.severity})")
    print(f"Service: {outcome.diagnosis.service_needed}")
    print(f"Provider: {outcome.dispatch.provider_name}")

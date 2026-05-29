"""Demo Scenario 2 — Photo-driven diagnosis.

The customer uploads a photo of a flat tire instead of writing text. TriageAgent
calls vision_tool, which calls Claude with the image and returns a structured
diagnosis. Tire-service provider gets dispatched.

Expected timeline
-----------------
REPORTED → ANALYZING (vision) → ASSIGNED to tire-service provider → both notified.
"""
from __future__ import annotations

import json

import pytest

from app.agents.base import AgentContext
from app.agents.orchestrator import OrchestratorAgent
from app.models.enums import IncidentStatus, IncidentSeverity, ServiceType
from app.schemas.diagnosis import DiagnosisResult

from tests.demo.conftest import (
    fake_anthropic_router,
    seed_customer,
    seed_incident,
    seed_provider,
)


@pytest.mark.asyncio
async def test_scenario_2_photo(db_session, bus, monkeypatch, capsys):
    # ----- Seed -----
    customer = await seed_customer(db_session, phone="+15551111002")
    # Seed a tire-service provider closer than a generic mechanic
    tire_user, _ = await seed_provider(
        db_session, phone="+15552222010", name="Mike TireBattery",
        lat=37.7749, lng=-122.4194, service_type="tire",
    )

    incident = await seed_incident(
        db_session, customer_id=customer.id,
        description=None,  # no text — diagnose from photo
        image_url="/uploads/demo_flat_tire.jpg",
    )

    # ----- Stub vision_tool to skip Anthropic image upload -----
    # NB: triage imports `analyze_vehicle_image` by name at module-load, so we
    # must patch the binding inside `app.agents.triage`, not the source module.
    from app.tools import vision_tool
    from app.agents import triage as triage_mod

    async def _fake_vision(image_url, *, anthropic_client=None, model=None):
        return DiagnosisResult(
            issue_type="flat rear-right tire",
            severity=IncidentSeverity.medium,
            service_needed=ServiceType.tire,
            confidence=0.92,
            details="Photo shows fully deflated rear-right tire. Bring tire-change kit or spare.",
        )

    monkeypatch.setattr(vision_tool, "analyze_vehicle_image", _fake_vision)
    monkeypatch.setattr(triage_mod, "analyze_vehicle_image", _fake_vision)

    # ----- Stub guardrail + comm -----
    client = fake_anthropic_router({
        # Triage falls through to image branch; no text-diagnosis call
        "strict security classifier": json.dumps({
            "safe": True, "reason": "no text input", "sanitized": "", "patterns": [],
        }),
        "roadside-assistance platform":
            "Help on the way — Mike will replace your flat tire in about 6 minutes.",
    })

    # ----- Run -----
    orch = OrchestratorAgent(anthropic_client=client)
    result = await orch.run(AgentContext(db=db_session, incident_id=incident.id))
    assert result.success, result.error
    outcome = result.output

    # DiagnosisResult uses ConfigDict(use_enum_values=True) so the enum is
    # flattened to its string value on the model.
    assert outcome.diagnosis.service_needed == ServiceType.tire.value
    assert outcome.dispatch.assigned is True
    assert outcome.dispatch.provider_id == tire_user.id

    await db_session.refresh(incident)
    assert incident.status == IncidentStatus.ASSIGNED.value

    print("\n=== Scenario 2: Photo upload ===")
    print(f"Diagnosis from vision: {outcome.diagnosis.issue_type}")
    print(f"Service routed to: {outcome.diagnosis.service_needed}")
    print(f"Provider: {outcome.dispatch.provider_name}")
    print(f"Messages sent: {len(bus.sent_messages)}")

"""Tests for vision_tool parser, transcription dev fallback, and TriageAgent."""
from __future__ import annotations

import json
import os
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.agents.base import AgentContext
from app.agents.triage import TriageAgent
from app.models.enums import IncidentSeverity, ServiceType
from app.tools.transcription_tool import (
    TranscriptionError,
    transcribe_voice_note,
)
from app.tools.vision_tool import VisionToolError, parse_diagnosis


# ============================================================
# Section 1 — Vision parser (pure unit tests)
# ============================================================


def test_parses_valid_diagnosis():
    raw = json.dumps({
        "issue_type": "flat tire",
        "severity": "medium",
        "service_needed": "tire",
        "confidence": 0.9,
        "details": "Front-left tire fully deflated, sidewall damage visible.",
    })
    d = parse_diagnosis(raw)
    assert d.issue_type == "flat tire"
    assert d.severity == IncidentSeverity.medium.value
    assert d.service_needed == ServiceType.tire.value
    assert d.confidence == 0.9


def test_handles_code_fence_wrapping():
    raw = '```json\n{"issue_type": "dead battery", "severity": "low", "service_needed": "battery", "confidence": 0.8}\n```'
    d = parse_diagnosis(raw)
    assert d.service_needed == ServiceType.battery.value


def test_rejects_hallucinated_service_type():
    raw = json.dumps({
        "issue_type": "weird issue", "severity": "medium",
        "service_needed": "spaceship_repair",  # not in enum
        "confidence": 0.5,
    })
    with pytest.raises(VisionToolError, match="unknown service_needed"):
        parse_diagnosis(raw)


def test_unknown_severity_coerced_to_unknown():
    raw = json.dumps({
        "issue_type": "x", "severity": "catastrophic",  # not in enum
        "service_needed": "mechanic", "confidence": 0.5,
    })
    d = parse_diagnosis(raw)
    assert d.severity == IncidentSeverity.unknown.value


def test_confidence_clamped_to_range():
    raw = json.dumps({
        "issue_type": "x", "severity": "low",
        "service_needed": "mechanic", "confidence": 99.0,  # out of range
    })
    d = parse_diagnosis(raw)
    assert d.confidence == 1.0


def test_confidence_clamped_lower():
    raw = json.dumps({
        "issue_type": "x", "severity": "low",
        "service_needed": "mechanic", "confidence": -5.0,
    })
    d = parse_diagnosis(raw)
    assert d.confidence == 0.0


def test_non_numeric_confidence_defaults_to_zero():
    raw = json.dumps({
        "issue_type": "x", "severity": "low",
        "service_needed": "mechanic", "confidence": "high",
    })
    d = parse_diagnosis(raw)
    assert d.confidence == 0.0


def test_empty_response_raises():
    with pytest.raises(VisionToolError):
        parse_diagnosis("")


def test_non_json_raises():
    with pytest.raises(VisionToolError):
        parse_diagnosis("not json")


def test_non_object_json_raises():
    with pytest.raises(VisionToolError):
        parse_diagnosis("[1, 2, 3]")


# ============================================================
# Section 2 — Transcription dev fallback
# ============================================================


@pytest.mark.asyncio
async def test_transcription_dev_returns_placeholder():
    """With STT_PROVIDER unset, the dev placeholder is returned."""
    os.environ.pop("STT_PROVIDER", None)
    text = await transcribe_voice_note("/tmp/some_audio.webm")
    assert "transcription unavailable" in text.lower()
    assert "some_audio.webm" in text


@pytest.mark.asyncio
async def test_transcription_empty_source_raises():
    with pytest.raises(TranscriptionError):
        await transcribe_voice_note("")


@pytest.mark.asyncio
async def test_unknown_provider_raises():
    os.environ["STT_PROVIDER"] = "no-such-provider"
    try:
        with pytest.raises(TranscriptionError, match="unknown STT_PROVIDER"):
            await transcribe_voice_note("/tmp/x.wav")
    finally:
        os.environ.pop("STT_PROVIDER", None)


# ============================================================
# Section 3 — TriageAgent (mocked Claude, no DB needed)
# ============================================================


def _mock_anthropic_with(text_response: str) -> MagicMock:
    block = MagicMock()
    block.type = "text"
    block.text = text_response
    response = MagicMock()
    response.content = [block]
    client = MagicMock()
    client.messages = MagicMock()
    client.messages.create = AsyncMock(return_value=response)
    return client


def _make_context(db_session, **payload) -> AgentContext:
    return AgentContext(db=db_session, payload=payload)


@pytest.mark.asyncio
async def test_triage_text_only(db_session):
    client = _mock_anthropic_with(json.dumps({
        "issue_type": "dead battery",
        "severity": "medium",
        "service_needed": "battery",
        "confidence": 0.85,
        "details": "Customer reports car won't start after lights left on.",
    }))
    agent = TriageAgent(anthropic_client=client)
    ctx = _make_context(
        db_session,
        description="My car won't start. I left the lights on overnight.",
    )
    result = await agent.run(ctx)
    assert result.success
    assert result.output.issue_type == "dead battery"
    assert result.output.service_needed == ServiceType.battery.value


@pytest.mark.asyncio
async def test_triage_requires_at_least_one_input(db_session):
    """No description, no image, no voice → AgentExecutionError."""
    client = _mock_anthropic_with("{}")
    agent = TriageAgent(anthropic_client=client)
    ctx = _make_context(db_session)
    result = await agent.run(ctx)
    assert result.success is False
    assert "at least one" in result.error.lower()


@pytest.mark.asyncio
async def test_triage_returns_unknown_on_parse_failure(db_session):
    """Garbage Claude output → unknown diagnosis, not a guess."""
    client = _mock_anthropic_with("this is not json")
    agent = TriageAgent(anthropic_client=client)
    ctx = _make_context(db_session, description="something")
    result = await agent.run(ctx)
    assert result.success
    assert result.output.issue_type == "unknown"
    assert result.output.severity == IncidentSeverity.unknown.value
    assert result.output.confidence == 0.0


@pytest.mark.asyncio
async def test_triage_voice_merged_into_description(db_session):
    """Voice transcription should be appended to description before diagnosis."""
    os.environ.pop("STT_PROVIDER", None)  # dev placeholder
    client = _mock_anthropic_with(json.dumps({
        "issue_type": "engine overheating",
        "severity": "high",
        "service_needed": "mechanic",
        "confidence": 0.7,
    }))
    agent = TriageAgent(anthropic_client=client)
    ctx = _make_context(
        db_session,
        description="Steam coming out of hood",
        voice_url="/tmp/note.webm",
    )
    result = await agent.run(ctx)
    assert result.success
    assert result.output.issue_type == "engine overheating"
    # Verify the merged description was passed to Claude
    call_kwargs = client.messages.create.call_args.kwargs
    user_msg = call_kwargs["messages"][0]["content"]
    assert "Steam coming out" in user_msg
    assert "transcription unavailable" in user_msg.lower()  # dev placeholder text


@pytest.mark.asyncio
async def test_triage_tool_authorization(db_session):
    """TriageAgent's tool allow-list must NOT include any write tool."""
    agent = TriageAgent(anthropic_client=_mock_anthropic_with("{}"))
    assert "vision_tool" in agent.tools
    assert "transcription_tool" in agent.tools
    # Negative: confirm a write tool would be rejected
    from app.agents.base import ToolNotAuthorizedError
    with pytest.raises(ToolNotAuthorizedError):
        agent._check_tool_authorized("db_write_tool")
    with pytest.raises(ToolNotAuthorizedError):
        agent._check_tool_authorized("twilio_tool")


@pytest.mark.asyncio
async def test_triage_hallucinated_service_returns_unknown(db_session):
    """If Claude invents a service type, fall through to unknown."""
    client = _mock_anthropic_with(json.dumps({
        "issue_type": "weird", "severity": "medium",
        "service_needed": "alien_abduction_recovery",
        "confidence": 0.6,
    }))
    agent = TriageAgent(anthropic_client=client)
    ctx = _make_context(db_session, description="something strange")
    result = await agent.run(ctx)
    assert result.success
    assert result.output.issue_type == "unknown"
    assert result.output.service_needed == ServiceType.other.value

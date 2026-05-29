"""TriageAgent — diagnose a vehicle issue from text, image, voice, or any combination.

Inputs (via AgentContext.payload):
    - description: str | None      — free-text customer description
    - image_url:   str | None      — URL or path to vehicle photo
    - voice_url:   str | None      — URL or path to voice note

Output: DiagnosisResult (validated; service_needed always within ServiceType enum).

Behavior:
- If image_url present, call vision_tool → primary structured diagnosis.
- If voice_url present, call transcription_tool, merge transcript into description.
- If only text is present, call Claude on the description.
- On ambiguous input (no signal, conflicting signals), return severity=unknown
  with confidence < 0.4 — never guess.
- Tools allow-list strictly enforced: vision_tool, transcription_tool only.
  This agent CANNOT write to the database; it produces structured advice only.
"""
from __future__ import annotations

import json
from typing import Any

from anthropic import AsyncAnthropic

from app.agents.base import AgentContext, AgentExecutionError, BaseAgent
from app.middleware.logging import get_logger
from app.models.enums import IncidentSeverity, ServiceType
from app.schemas.diagnosis import DiagnosisResult
from app.tools.transcription_tool import TranscriptionError, transcribe_voice_note
from app.tools.vision_tool import (
    VisionToolError,
    analyze_vehicle_image,
    parse_diagnosis,
)

log = get_logger("agents.triage")


# ----------------------------------------------------------------------
# Text-only diagnosis prompt
# ----------------------------------------------------------------------


def _text_diagnosis_system_prompt() -> str:
    services = ", ".join(s.value for s in ServiceType)
    severities = ", ".join(s.value for s in IncidentSeverity)
    return f"""You are an expert roadside-assistance vehicle diagnostician.

Read the customer's description of their breakdown and produce a strictly
structured diagnosis. The description may be brief, garbled, or non-technical.
Never invent symptoms not mentioned. When in doubt, return severity="unknown"
with confidence below 0.4 — do not guess.

Constraints:
- `service_needed` MUST be exactly one of: {services}
- `severity` MUST be exactly one of: {severities}
- `issue_type` is a short human-readable label (max 100 chars)
- `details` (optional) — what the responding provider should bring/expect

Output ONLY this JSON object, no prose before or after:
{{"issue_type": "...", "severity": "...", "service_needed": "...", "confidence": 0.0, "details": "..."}}
"""


# ----------------------------------------------------------------------
# TriageAgent
# ----------------------------------------------------------------------


class TriageAgent(BaseAgent[DiagnosisResult]):
    name = "TriageAgent"
    persona = (
        "Expert vehicle diagnostician with 20 years of roadside-assistance experience. "
        "Calm, precise, never guesses. Knows the difference between what the customer "
        "said, what they showed, and what they meant."
    )
    goal = "Produce an accurate structured diagnosis from any combination of text, image, and voice."
    max_tokens = 600
    # Tools this agent is authorized to invoke. No db_write.
    tools = ("vision_tool", "transcription_tool")

    async def _execute(self, context: AgentContext) -> DiagnosisResult:
        payload = context.payload
        description: str | None = payload.get("description")
        image_url: str | None = payload.get("image_url")
        voice_url: str | None = payload.get("voice_url")

        if not any([description, image_url, voice_url]):
            raise AgentExecutionError(
                "TriageAgent requires at least one of: description, image_url, voice_url"
            )

        # ----- Step 1: voice → text, merge into description -----
        if voice_url:
            self._check_tool_authorized("transcription_tool")
            try:
                transcript = await transcribe_voice_note(voice_url)
            except TranscriptionError as exc:
                log.warning("transcription_failed", error=str(exc))
                transcript = ""
            if transcript:
                description = (description + " " if description else "") + transcript

        # ----- Step 2: if image present, vision is the primary signal -----
        if image_url:
            self._check_tool_authorized("vision_tool")
            try:
                diagnosis = await analyze_vehicle_image(
                    image_url, anthropic_client=self._client
                )
            except VisionToolError as exc:
                log.warning("vision_failed", error=str(exc))
                # Fall through to text-only path if we still have description
                if description:
                    diagnosis = await self._diagnose_from_text(description)
                else:
                    return self._unknown_diagnosis(f"vision failed: {exc}")
            else:
                # If we ALSO have description, lightly enrich the details field
                if description and not diagnosis.details:
                    diagnosis = diagnosis.model_copy(
                        update={"details": description[:500]}
                    )
            return diagnosis

        # ----- Step 3: text-only path -----
        if description:
            return await self._diagnose_from_text(description)

        # Should never reach here given the early-return guard above
        return self._unknown_diagnosis("no usable input")

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    async def _diagnose_from_text(self, description: str) -> DiagnosisResult:
        """Run Claude on a text description and parse the structured response."""
        try:
            raw = await self._call_claude(
                system=_text_diagnosis_system_prompt(),
                messages=[{"role": "user", "content": description}],
                max_tokens=self.max_tokens,
                temperature=0.0,
            )
        except Exception as exc:
            log.warning("text_diagnosis_call_failed", error=str(exc))
            return self._unknown_diagnosis(f"diagnosis call failed: {exc}")

        try:
            return parse_diagnosis(raw)
        except VisionToolError as exc:
            # Parser is shared with vision_tool; same JSON shape applies here.
            log.warning("text_diagnosis_parse_failed", error=str(exc))
            return self._unknown_diagnosis(str(exc))

    @staticmethod
    def _unknown_diagnosis(reason: str) -> DiagnosisResult:
        """Deterministic 'I don't know' diagnosis — preferred over guessing."""
        return DiagnosisResult(
            issue_type="unknown",
            severity=IncidentSeverity.unknown,
            service_needed=ServiceType.other,
            confidence=0.0,
            details=f"Triage could not classify confidently. {reason}"[:1000],
        )

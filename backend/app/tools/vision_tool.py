"""Vision tool — diagnose a vehicle issue from a single image.

Used by TriageAgent. The output is a strictly validated `DiagnosisResult` —
any service_needed value outside the `ServiceType` enum is rejected so the
DispatchAgent never sees a hallucinated category.

Inputs: a URL (http/https) OR a local filesystem path (under `UPLOAD_DIR`).
Local paths are read directly to avoid an extra HTTP hop.
"""
from __future__ import annotations

import base64
import json
import os
from pathlib import Path

import httpx
from anthropic import AsyncAnthropic

from app.config import settings
from app.middleware.logging import get_logger
from app.models.enums import IncidentSeverity, ServiceType
from app.schemas.diagnosis import DiagnosisResult

log = get_logger("tools.vision")


# ----------------------------------------------------------------------
# Prompt — structured JSON output, strict enum constraints
# ----------------------------------------------------------------------


def _build_system_prompt() -> str:
    services = ", ".join(s.value for s in ServiceType)
    severities = ", ".join(s.value for s in IncidentSeverity)
    return f"""You are an expert roadside-assistance vehicle diagnostician.

Look at the image of a vehicle and produce a strictly structured diagnosis.

Constraints:
- `service_needed` MUST be exactly one of: {services}
- `severity` MUST be exactly one of: {severities}
- If the image does not clearly show a vehicle issue, return severity="unknown" and confidence < 0.4
- `issue_type` is a short human-readable label (max 100 chars)
- `details` are optional supporting notes (max 1000 chars) — what the provider should bring or expect

Output ONLY this JSON object, with no prose before or after:
{{"issue_type": "...", "severity": "...", "service_needed": "...", "confidence": 0.0, "details": "..."}}
"""


# ----------------------------------------------------------------------
# Image loading
# ----------------------------------------------------------------------


_MEDIA_TYPES = {
    ".jpg": "image/jpeg", ".jpeg": "image/jpeg",
    ".png": "image/png", ".webp": "image/webp",
    ".gif": "image/gif",
}


class VisionToolError(Exception):
    pass


async def _load_image_b64(source: str) -> tuple[str, str]:
    """Return (base64_data, media_type) for either a URL or a local file path."""
    # Local file?
    if not source.startswith(("http://", "https://")):
        path = Path(source)
        if not path.exists():
            raise VisionToolError(f"image file not found: {source}")
        suffix = path.suffix.lower()
        if suffix not in _MEDIA_TYPES:
            raise VisionToolError(f"unsupported image extension: {suffix}")
        data = path.read_bytes()
        return base64.standard_b64encode(data).decode("ascii"), _MEDIA_TYPES[suffix]

    # Remote URL
    async with httpx.AsyncClient(timeout=15.0) as client:
        resp = await client.get(source)
        if resp.status_code != 200:
            raise VisionToolError(f"image fetch failed: HTTP {resp.status_code}")
        media_type = resp.headers.get("content-type", "image/jpeg").split(";")[0].strip()
        if media_type not in _MEDIA_TYPES.values():
            # Last-resort: trust suffix
            ext = os.path.splitext(source.split("?")[0])[1].lower()
            media_type = _MEDIA_TYPES.get(ext, "image/jpeg")
        return base64.standard_b64encode(resp.content).decode("ascii"), media_type


# ----------------------------------------------------------------------
# Strict response parser — hallucination-rejecting
# ----------------------------------------------------------------------


def parse_diagnosis(raw_text: str) -> DiagnosisResult:
    """Parse the Claude vision response into a validated DiagnosisResult.

    Raises VisionToolError on any malformed response or out-of-enum value.
    """
    if not raw_text:
        raise VisionToolError("empty response from vision model")

    cleaned = raw_text.strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.split("\n", 1)[1] if "\n" in cleaned else cleaned[3:]
    if cleaned.endswith("```"):
        cleaned = cleaned.rsplit("```", 1)[0].strip()

    try:
        data = json.loads(cleaned)
    except json.JSONDecodeError as exc:
        raise VisionToolError(f"vision response is not valid JSON: {exc}") from exc

    if not isinstance(data, dict):
        raise VisionToolError("vision response was not a JSON object")

    # Validate enums before Pydantic to give a clearer error message
    service = data.get("service_needed")
    if service not in {s.value for s in ServiceType}:
        raise VisionToolError(
            f"vision returned unknown service_needed='{service}'. "
            f"Allowed: {[s.value for s in ServiceType]}"
        )

    sev = data.get("severity", "unknown")
    if sev not in {s.value for s in IncidentSeverity}:
        # Coerce unrecognized severities to 'unknown' rather than reject — the
        # dispatcher can still proceed; severity is advisory.
        data["severity"] = IncidentSeverity.unknown.value

    # Clamp confidence to [0, 1] if model returned out-of-range
    conf = data.get("confidence")
    if isinstance(conf, (int, float)):
        data["confidence"] = max(0.0, min(1.0, float(conf)))
    else:
        data["confidence"] = 0.0

    try:
        return DiagnosisResult.model_validate(data)
    except Exception as exc:
        raise VisionToolError(f"vision response failed schema validation: {exc}") from exc


# ----------------------------------------------------------------------
# Public entry point
# ----------------------------------------------------------------------


async def analyze_vehicle_image(
    image_source: str,
    *,
    anthropic_client: AsyncAnthropic | None = None,
) -> DiagnosisResult:
    """Run Claude vision on the given image and return a validated DiagnosisResult."""
    client = anthropic_client or (
        AsyncAnthropic(api_key=settings.ANTHROPIC_API_KEY)
        if settings.ANTHROPIC_API_KEY
        else None
    )
    if client is None:
        raise VisionToolError(
            "ANTHROPIC_API_KEY missing — cannot call vision model"
        )

    b64, media_type = await _load_image_b64(image_source)

    response = await client.messages.create(
        model=settings.CLAUDE_MODEL,
        max_tokens=400,
        temperature=0.0,
        system=_build_system_prompt(),
        messages=[
            {
                "role": "user",
                "content": [
                    {
                        "type": "image",
                        "source": {
                            "type": "base64",
                            "media_type": media_type,
                            "data": b64,
                        },
                    },
                    {
                        "type": "text",
                        "text": "Diagnose the vehicle issue shown. Output only the JSON.",
                    },
                ],
            }
        ],
    )

    # Pull the first text block
    text = ""
    for block in response.content:
        if getattr(block, "type", None) == "text":
            text = block.text
            break

    diagnosis = parse_diagnosis(text)
    log.info(
        "vision_diagnosis",
        issue_type=diagnosis.issue_type,
        severity=diagnosis.severity,
        service=diagnosis.service_needed,
        confidence=diagnosis.confidence,
    )
    return diagnosis

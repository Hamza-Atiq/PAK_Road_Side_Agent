"""Voice-note transcription tool.

Design note
-----------
Claude does not currently have native audio-input support, so transcription
is delegated to a third-party Speech-To-Text (STT) provider. This module
defines a clean interface and ships with a **dev-mode placeholder** that
returns a clearly-marked string, so the TriageAgent flow runs end-to-end
without blocking on a provider choice.

To wire in a real provider, implement `_transcribe_<provider>()` and add a
case to `transcribe_voice_note()`. Recommended providers:

  - **OpenAI Whisper** (cheap, accurate, multi-language) — `openai` SDK
  - **AssemblyAI** (great accuracy + speaker diarization)
  - **Deepgram** (fastest, streaming-ready)

Each implementation should: load the audio, send to the provider, return
plain UTF-8 text, raise `TranscriptionError` on failure.

Configuration
-------------
- `STT_PROVIDER` env var: "dev" (default) | "openai" | "assemblyai" | "deepgram"
- `STT_API_KEY` env var: provider API key
- Max audio length: enforced by upload size limit (`MAX_UPLOAD_MB`)
- Max output text: 5000 chars (truncated)
"""
from __future__ import annotations

import os
from pathlib import Path

import httpx

from app.middleware.logging import get_logger

log = get_logger("tools.transcription")

MAX_TRANSCRIPT_CHARS = 5000


class TranscriptionError(Exception):
    pass


# ----------------------------------------------------------------------
# Dev / placeholder implementation
# ----------------------------------------------------------------------


def _transcribe_dev(source: str) -> str:
    """Dev-mode placeholder: returns a clearly-marked placeholder string.

    This is intentionally explicit so it can't accidentally be mistaken for
    a real transcription in downstream agent logic.
    """
    log.warning(
        "stt_dev_placeholder",
        source=source,
        message="STT provider not configured — using placeholder transcription",
    )
    filename = Path(source).name if not source.startswith("http") else source
    return (
        f"[transcription unavailable — STT_PROVIDER not configured. "
        f"audio source: {filename}]"
    )


# ----------------------------------------------------------------------
# Audio loading
# ----------------------------------------------------------------------


async def _load_audio_bytes(source: str) -> bytes:
    """Read audio either from a local file or HTTP URL."""
    if not source.startswith(("http://", "https://")):
        path = Path(source)
        if not path.exists():
            raise TranscriptionError(f"audio file not found: {source}")
        return path.read_bytes()

    async with httpx.AsyncClient(timeout=30.0) as client:
        resp = await client.get(source)
        if resp.status_code != 200:
            raise TranscriptionError(f"audio fetch failed: HTTP {resp.status_code}")
        return resp.content


# ----------------------------------------------------------------------
# Provider: OpenAI Whisper (stub — implement when openai SDK is added)
# ----------------------------------------------------------------------


async def _transcribe_openai(source: str) -> str:  # pragma: no cover — provider stub
    """Whisper-1 via OpenAI's audio transcription API.

    Activation: `pip install openai`, set STT_PROVIDER=openai, STT_API_KEY=sk-...
    Cost: ~$0.006/minute as of 2026.
    """
    raise TranscriptionError(
        "OpenAI Whisper not wired up. Install `openai`, set STT_PROVIDER=openai, "
        "and replace this stub with an actual client call."
    )


async def _transcribe_assemblyai(source: str) -> str:  # pragma: no cover — provider stub
    raise TranscriptionError("AssemblyAI provider not wired up.")


async def _transcribe_deepgram(source: str) -> str:  # pragma: no cover — provider stub
    raise TranscriptionError("Deepgram provider not wired up.")


# ----------------------------------------------------------------------
# Public entry point
# ----------------------------------------------------------------------


async def transcribe_voice_note(audio_source: str) -> str:
    """Transcribe an audio file or URL into plain UTF-8 text.

    Returns a non-empty string. Raises TranscriptionError on hard failures.
    """
    if not audio_source:
        raise TranscriptionError("audio_source is required")

    provider = os.environ.get("STT_PROVIDER", "dev").lower()

    if provider == "dev":
        text = _transcribe_dev(audio_source)
    elif provider == "openai":
        text = await _transcribe_openai(audio_source)
    elif provider == "assemblyai":
        text = await _transcribe_assemblyai(audio_source)
    elif provider == "deepgram":
        text = await _transcribe_deepgram(audio_source)
    else:
        raise TranscriptionError(f"unknown STT_PROVIDER: {provider!r}")

    if not text:
        raise TranscriptionError("transcription returned empty text")

    if len(text) > MAX_TRANSCRIPT_CHARS:
        text = text[:MAX_TRANSCRIPT_CHARS] + "…"

    return text

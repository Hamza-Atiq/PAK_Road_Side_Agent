"""Upload validation and storage.

Validates MIME by sniffing bytes (python-magic), not just file extension —
extensions can be spoofed but file headers can't be (easily). Stores files
under `UPLOAD_DIR` with a random UUID filename so original names can't be
used for path traversal or as injection vectors in downstream tools.

Returned URLs are absolute when `APP_BASE_URL` is set, otherwise relative
(`/uploads/{id}{ext}`). The FastAPI app mounts UPLOAD_DIR at `/uploads`.
"""
from __future__ import annotations

import uuid
from pathlib import Path
from typing import Literal

import magic
from fastapi import UploadFile

from app.config import settings
from app.middleware.logging import get_logger

log = get_logger("services.file")

FileKind = Literal["image", "audio"]

_EXT_BY_MIME: dict[str, str] = {
    "image/jpeg": ".jpg",
    "image/png": ".png",
    "image/webp": ".webp",
    "image/gif": ".gif",
    "audio/mpeg": ".mp3",
    "audio/mp4": ".m4a",
    "audio/wav": ".wav",
    "audio/x-wav": ".wav",
    "audio/webm": ".webm",
    "audio/ogg": ".ogg",
}


class UploadValidationError(Exception):
    """Raised when an upload fails MIME or size validation."""


# ----------------------------------------------------------------------
# Validation helpers
# ----------------------------------------------------------------------


def _sniff_mime(data: bytes) -> str:
    """Return the real MIME type by sniffing the first bytes.

    We check well-known magic-byte signatures for the formats we support before
    falling back to libmagic. This is deterministic across platforms — libmagic's
    bundled databases differ between Linux's `file`, python-magic-bin on Windows,
    and Homebrew installs, and have produced false negatives for short PNGs and
    "audio/x-wav" vs "audio/wav" inconsistencies. The fallback to libmagic is
    kept so we can still catch spoofed uploads (e.g. HTML masquerading as .jpg).
    """
    if not data:
        return "application/octet-stream"
    head = data[:16]
    # Images
    if head.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if head.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if head[:4] == b"RIFF" and head[8:12] == b"WEBP":
        return "image/webp"
    # Audio
    if head[:4] == b"RIFF" and head[8:12] == b"WAVE":
        return "audio/wav"
    if head[:3] == b"ID3" or head[:2] == b"\xff\xfb" or head[:2] == b"\xff\xf3":
        return "audio/mpeg"
    if head[:4] == b"OggS":
        return "audio/ogg"
    if head[:4] == b"\x1aE\xdf\xa3":  # EBML — covers webm
        return "audio/webm"
    if head[4:8] == b"ftyp":
        return "audio/mp4"
    return magic.from_buffer(data[:8192], mime=True)


def _allowed_mimes_for(kind: FileKind) -> list[str]:
    if kind == "image":
        return settings.allowed_image_mimes
    return settings.allowed_audio_mimes


def _extension_for(mime: str) -> str:
    return _EXT_BY_MIME.get(mime, ".bin")


# ----------------------------------------------------------------------
# Public API
# ----------------------------------------------------------------------


async def save_uploaded_file(upload: UploadFile, *, kind: FileKind) -> str:
    """Validate and persist an uploaded file. Returns a URL the agent can pass
    to vision_tool / transcription_tool.

    Raises UploadValidationError if the upload fails MIME or size checks.
    """
    if upload is None or upload.filename is None:
        raise UploadValidationError("no file uploaded")

    data = await upload.read()
    size = len(data)
    if size == 0:
        raise UploadValidationError("uploaded file is empty")
    if size > settings.max_upload_bytes:
        raise UploadValidationError(
            f"file too large ({size} bytes, max {settings.max_upload_bytes})"
        )

    sniffed = _sniff_mime(data)
    allowed = _allowed_mimes_for(kind)
    if sniffed not in allowed:
        raise UploadValidationError(
            f"unsupported {kind} MIME '{sniffed}'. Allowed: {allowed}"
        )

    file_id = uuid.uuid4().hex
    ext = _extension_for(sniffed)
    filename = f"{file_id}{ext}"

    upload_dir = Path(settings.UPLOAD_DIR).resolve()
    upload_dir.mkdir(parents=True, exist_ok=True)
    target = upload_dir / filename
    target.write_bytes(data)

    base = settings.APP_BASE_URL.rstrip("/") if settings.APP_BASE_URL else ""
    url = f"{base}/uploads/{filename}" if base else f"/uploads/{filename}"

    log.info(
        "file_saved",
        kind=kind,
        mime=sniffed,
        size_bytes=size,
        filename=filename,
        url=url,
    )
    return url

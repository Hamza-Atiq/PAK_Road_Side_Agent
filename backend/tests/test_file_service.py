"""Unit tests for the upload validation/storage helpers (no DB needed)."""
from __future__ import annotations

import io
from unittest.mock import MagicMock

import pytest
from fastapi import UploadFile

from app.services.file_service import (
    UploadValidationError,
    _extension_for,
    _sniff_mime,
    save_uploaded_file,
)


# PNG magic header — 8 bytes
PNG_BYTES = b"\x89PNG\r\n\x1a\n" + b"\x00" * 64
# WAV header (RIFF...WAVE...)
WAV_BYTES = b"RIFF" + (len(b"x" * 32) + 36).to_bytes(4, "little") + b"WAVE" + b"x" * 32
# A clearly non-image / non-audio: HTML doc
HTML_BYTES = b"<!DOCTYPE html><html><body>hi</body></html>"


def _upload(name: str, data: bytes) -> UploadFile:
    return UploadFile(filename=name, file=io.BytesIO(data))


def test_sniff_png():
    assert _sniff_mime(PNG_BYTES) == "image/png"


def test_sniff_empty_returns_octet_stream():
    assert _sniff_mime(b"") == "application/octet-stream"


def test_extension_for_known_and_unknown_mimes():
    assert _extension_for("image/jpeg") == ".jpg"
    assert _extension_for("image/png") == ".png"
    assert _extension_for("audio/wav") == ".wav"
    assert _extension_for("application/x-totally-made-up") == ".bin"


@pytest.mark.asyncio
async def test_image_upload_persists_file(tmp_path, monkeypatch):
    """A real PNG → MIME passes, file is written with random name + correct extension."""
    from app.services import file_service
    monkeypatch.setattr(file_service.settings, "UPLOAD_DIR", str(tmp_path))
    monkeypatch.setattr(file_service.settings, "APP_BASE_URL", "")
    url = await save_uploaded_file(_upload("user-upload.PNG", PNG_BYTES), kind="image")
    assert url.startswith("/uploads/")
    assert url.endswith(".png")
    # File exists on disk
    written = tmp_path / url.split("/")[-1]
    assert written.exists()
    assert written.read_bytes() == PNG_BYTES


@pytest.mark.asyncio
async def test_audio_upload_persists(tmp_path, monkeypatch):
    from app.services import file_service
    monkeypatch.setattr(file_service.settings, "UPLOAD_DIR", str(tmp_path))
    monkeypatch.setattr(file_service.settings, "APP_BASE_URL", "")
    url = await save_uploaded_file(_upload("note.wav", WAV_BYTES), kind="audio")
    assert url.endswith(".wav")


@pytest.mark.asyncio
async def test_html_uploaded_as_image_rejected(tmp_path, monkeypatch):
    """Extension spoof: .jpg filename containing HTML — MIME sniff must reject."""
    from app.services import file_service
    monkeypatch.setattr(file_service.settings, "UPLOAD_DIR", str(tmp_path))
    with pytest.raises(UploadValidationError, match="unsupported image MIME"):
        await save_uploaded_file(_upload("evil.jpg", HTML_BYTES), kind="image")


@pytest.mark.asyncio
async def test_oversized_upload_rejected(tmp_path, monkeypatch):
    from app.services import file_service
    monkeypatch.setattr(file_service.settings, "UPLOAD_DIR", str(tmp_path))
    # Force max bytes very small via the property's underlying setting
    monkeypatch.setattr(file_service.settings, "MAX_UPLOAD_MB", 0.0001)  # ~104 bytes
    with pytest.raises(UploadValidationError, match="too large"):
        await save_uploaded_file(_upload("big.png", PNG_BYTES * 10), kind="image")


@pytest.mark.asyncio
async def test_empty_upload_rejected(tmp_path, monkeypatch):
    from app.services import file_service
    monkeypatch.setattr(file_service.settings, "UPLOAD_DIR", str(tmp_path))
    with pytest.raises(UploadValidationError, match="empty"):
        await save_uploaded_file(_upload("empty.png", b""), kind="image")


@pytest.mark.asyncio
async def test_absolute_url_when_app_base_url_set(tmp_path, monkeypatch):
    from app.services import file_service
    monkeypatch.setattr(file_service.settings, "UPLOAD_DIR", str(tmp_path))
    monkeypatch.setattr(file_service.settings, "APP_BASE_URL", "https://api.test.example")
    url = await save_uploaded_file(_upload("a.png", PNG_BYTES), kind="image")
    assert url.startswith("https://api.test.example/uploads/")

"""Structured logging with trace_id per request and PII masking.

structlog emits JSON in production and human-readable output in dev.
Every request gets a unique `trace_id` bound to its context, so any log
inside that request can be correlated to the originating HTTP call.

PII masking processors run BEFORE the JSON renderer, so phone numbers
and lat/lng never appear in plaintext in logs.
"""
from __future__ import annotations

import logging
import re
import uuid
from contextvars import ContextVar
from typing import Any

import structlog
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from app.config import settings

# Per-request trace_id available to anything that imports get_trace_id()
trace_id_var: ContextVar[str | None] = ContextVar("trace_id", default=None)


_PHONE_RE = re.compile(r"(\+\d{1,3})(\d{3,})(\d{3,4})")
# Match isolated coords: not preceded by `:` (timestamps), not preceded by `T` (ISO date),
# require lat/lng-shaped integer prefix and ≥5 decimal places.
_COORD_RE = re.compile(r"(?<![:T\d.])(-?\d{1,3})\.(\d{5,})")


def mask_pii(_, __, event_dict: dict[str, Any]) -> dict[str, Any]:
    """Mask phone numbers and high-precision coordinates anywhere in the event dict.

    +15551234567 → +1555***4567
    37.7749123   → 37.7***
    """
    def _scrub(value: Any) -> Any:
        if isinstance(value, str):
            value = _PHONE_RE.sub(lambda m: f"{m.group(1)}***{m.group(3)}", value)
            value = _COORD_RE.sub(lambda m: f"{m.group(1)}.{m.group(2)[:1]}***", value)
            return value
        if isinstance(value, dict):
            return {k: _scrub(v) for k, v in value.items()}
        if isinstance(value, list):
            return [_scrub(v) for v in value]
        return value

    return {k: _scrub(v) for k, v in event_dict.items()}


def add_trace_id(_, __, event_dict: dict[str, Any]) -> dict[str, Any]:
    """Inject the current request's trace_id into every log line."""
    tid = trace_id_var.get()
    if tid:
        event_dict["trace_id"] = tid
    return event_dict


def configure_logging() -> None:
    """Call once at app startup. Idempotent."""
    log_level = logging.getLevelName(settings.LOG_LEVEL)

    # Quiet down noisy libraries
    logging.basicConfig(level=log_level, format="%(message)s")
    for noisy in ("sqlalchemy.engine", "uvicorn.access", "httpx"):
        logging.getLogger(noisy).setLevel(logging.WARNING)

    processors: list[Any] = [
        structlog.contextvars.merge_contextvars,
        structlog.processors.add_log_level,
        structlog.processors.TimeStamper(fmt="iso", utc=True),
        add_trace_id,
        mask_pii,
    ]

    if settings.APP_ENV == "development":
        processors.append(structlog.dev.ConsoleRenderer(colors=False))
    else:
        processors.append(structlog.processors.JSONRenderer())

    structlog.configure(
        processors=processors,
        wrapper_class=structlog.make_filtering_bound_logger(log_level),
        context_class=dict,
        cache_logger_on_first_use=True,
    )


def get_logger(name: str | None = None) -> structlog.BoundLogger:
    return structlog.get_logger(name)


def get_trace_id() -> str | None:
    return trace_id_var.get()


class TraceIDMiddleware(BaseHTTPMiddleware):
    """Stamp each request with a uuid4 trace_id, propagate as X-Trace-Id header."""

    async def dispatch(self, request: Request, call_next) -> Response:
        incoming = request.headers.get("X-Trace-Id")
        tid = incoming or uuid.uuid4().hex
        token = trace_id_var.set(tid)
        try:
            response = await call_next(request)
            response.headers["X-Trace-Id"] = tid
            return response
        finally:
            trace_id_var.reset(token)

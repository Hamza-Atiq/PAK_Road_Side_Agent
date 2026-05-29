"""HTTP request latency middleware + /metrics endpoint.

We instrument by **route template** (e.g. `/api/incidents/{incident_id}`),
not the raw URL — otherwise UUIDs would explode the label cardinality and
break Prometheus storage.
"""
from __future__ import annotations

import time

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import PlainTextResponse, Response
from starlette.routing import Match

from app.metrics import record_api_request, registry
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest


def _route_template(request: Request) -> str:
    """Find the parameterized template (e.g. '/api/incidents/{incident_id}').

    Falls back to the raw path if no route matched (404). We strip query
    strings so the label stays low-cardinality.
    """
    try:
        for route in request.app.router.routes:
            match, _ = route.matches(request.scope)
            if match == Match.FULL and getattr(route, "path", None):
                return route.path
    except Exception:  # noqa: BLE001 — middleware must never crash
        pass
    return request.url.path or "unknown"


class HTTPMetricsMiddleware(BaseHTTPMiddleware):
    """Times every request and records api_request_seconds."""

    async def dispatch(self, request: Request, call_next) -> Response:
        start = time.perf_counter()
        status_code = 500  # default if call_next raises before we get a response
        try:
            response = await call_next(request)
            status_code = response.status_code
            return response
        finally:
            duration = time.perf_counter() - start
            # Skip /metrics itself so the scrape doesn't poison the histogram
            if request.url.path != "/metrics":
                record_api_request(
                    method=request.method,
                    path=_route_template(request),
                    status_code=status_code,
                    duration_seconds=duration,
                )


def metrics_endpoint() -> PlainTextResponse:
    """Return the registry payload in Prometheus exposition format."""
    data = generate_latest(registry)
    return PlainTextResponse(content=data.decode("utf-8"), media_type=CONTENT_TYPE_LATEST)

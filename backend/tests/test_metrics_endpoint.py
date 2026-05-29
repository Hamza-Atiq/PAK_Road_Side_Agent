"""Tests for the /metrics HTTP endpoint exposed by FastAPI."""
from __future__ import annotations

import pytest

from app.metrics import incidents_created_total


@pytest.mark.asyncio
async def test_metrics_endpoint_returns_200_and_prometheus_format(client):
    resp = await client.get("/metrics")
    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("text/plain")
    body = resp.text
    assert "# TYPE" in body
    assert "incidents_created_total" in body


@pytest.mark.asyncio
async def test_metrics_endpoint_reflects_counter_increments(client):
    incidents_created_total.inc()
    resp = await client.get("/metrics")
    assert resp.status_code == 200
    # The body should include a non-zero value for incidents_created_total
    for line in resp.text.splitlines():
        if line.startswith("incidents_created_total ") and not line.startswith("#"):
            value = float(line.split()[-1])
            assert value >= 1.0
            return
    pytest.fail("incidents_created_total line not found")


@pytest.mark.asyncio
async def test_metrics_endpoint_path_not_recorded_in_api_histogram(client):
    """Calling /metrics shouldn't add itself to the api_request_seconds histogram —
    otherwise scrapes would skew the API latency stats."""
    # Snapshot the count for the /metrics route
    pre = await client.get("/metrics")
    assert pre.status_code == 200
    # Make a real request
    await client.get("/health")
    post = await client.get("/metrics")
    # /metrics should NOT appear as a path label
    assert 'path="/metrics"' not in post.text

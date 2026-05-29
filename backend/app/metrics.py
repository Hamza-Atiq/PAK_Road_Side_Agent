"""Prometheus metrics for the RoadSide Agent platform.

All metric definitions live here so there is exactly one canonical place
to discover what we measure. Each metric is registered against a single
module-level `CollectorRegistry` (NOT the global default) — that gives us
clean test isolation: a test can clear specific metrics without poisoning
the global state of `prometheus_client`.

If you need to add a new metric:
1. Define it below with the same naming convention (`<noun>_<unit>` or `_total` for counters).
2. Import the metric where you want to record it.
3. Add a panel reference in `infrastructure/grafana/dashboards/roadside.json`.
"""
from __future__ import annotations

from prometheus_client import CollectorRegistry, Counter, Gauge, Histogram

# A dedicated registry for the app's metrics. We expose only this one at
# /metrics — anything in the default registry (e.g. process_*) is included
# via `prometheus_client.process_collector` if mounted explicitly.
registry = CollectorRegistry(auto_describe=True)


# ----------------------------------------------------------------------
# Incident lifecycle counters
# ----------------------------------------------------------------------

incidents_created_total = Counter(
    "incidents_created_total",
    "Total incidents submitted by customers.",
    registry=registry,
)

incidents_assigned_total = Counter(
    "incidents_assigned_total",
    "Incidents successfully assigned to a provider.",
    registry=registry,
)

incidents_no_provider_total = Counter(
    "incidents_no_provider_total",
    "Incidents that reached NO_PROVIDER after full radius expansion.",
    registry=registry,
)

incidents_escalated_total = Counter(
    "incidents_escalated_total",
    "Incidents that reached ESCALATED state (human review required).",
    registry=registry,
)

# Histogram of REPORTED → ASSIGNED latency. The default buckets aren't ideal
# for sub-second/sub-minute ranges; tune for the 0.1-60s window we care about.
incident_processing_seconds = Histogram(
    "incident_processing_seconds",
    "Wall-clock seconds from REPORTED to ASSIGNED (orchestrator pipeline).",
    buckets=(0.5, 1.0, 2.0, 5.0, 10.0, 15.0, 30.0, 60.0, 120.0, 300.0),
    registry=registry,
)


# ----------------------------------------------------------------------
# Agent activity
# ----------------------------------------------------------------------

agent_calls_total = Counter(
    "agent_calls_total",
    "Number of times each agent has been invoked.",
    labelnames=("agent_name",),
    registry=registry,
)

agent_errors_total = Counter(
    "agent_errors_total",
    "Number of times each agent's run() returned success=False or raised.",
    labelnames=("agent_name",),
    registry=registry,
)

agent_duration_seconds = Histogram(
    "agent_duration_seconds",
    "Wall-clock seconds per agent.run() call.",
    labelnames=("agent_name",),
    buckets=(0.1, 0.5, 1.0, 2.0, 5.0, 10.0, 30.0, 60.0),
    registry=registry,
)


# ----------------------------------------------------------------------
# Guardrail
# ----------------------------------------------------------------------

guardrail_blocks_total = Counter(
    "guardrail_blocks_total",
    "Number of inputs blocked by GuardrailAgent as unsafe.",
    registry=registry,
)


# ----------------------------------------------------------------------
# Twilio / messaging
# ----------------------------------------------------------------------

sms_sent_total = Counter(
    "sms_sent_total",
    "Outbound messages handed to Twilio (sms or whatsapp).",
    labelnames=("channel",),
    registry=registry,
)

sms_failures_total = Counter(
    "sms_failures_total",
    "Twilio delivery failures (via status callback or send error).",
    labelnames=("channel",),
    registry=registry,
)


# ----------------------------------------------------------------------
# Tracking
# ----------------------------------------------------------------------

provider_offline_detections_total = Counter(
    "provider_offline_detections_total",
    "Times TrackingAgent flagged a provider as offline mid-job.",
    registry=registry,
)


# ----------------------------------------------------------------------
# Celery
# ----------------------------------------------------------------------

celery_tasks_active = Gauge(
    "celery_tasks_active",
    "Number of Celery tasks currently running on this worker.",
    labelnames=("queue",),
    registry=registry,
    multiprocess_mode="livesum",
)

celery_queue_length = Gauge(
    "celery_queue_length",
    "Pending tasks in the Redis broker for each queue.",
    labelnames=("queue",),
    registry=registry,
    multiprocess_mode="livesum",
)


# ----------------------------------------------------------------------
# HTTP
# ----------------------------------------------------------------------

api_request_seconds = Histogram(
    "api_request_seconds",
    "HTTP request latency.",
    labelnames=("method", "path", "status"),
    buckets=(0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0),
    registry=registry,
)


# ----------------------------------------------------------------------
# Recording helpers (typed sugar around the raw client API)
# ----------------------------------------------------------------------


def observe_incident_processing(duration_seconds: float) -> None:
    incident_processing_seconds.observe(duration_seconds)


def record_agent_call(agent_name: str, *, success: bool, duration_seconds: float) -> None:
    agent_calls_total.labels(agent_name=agent_name).inc()
    agent_duration_seconds.labels(agent_name=agent_name).observe(duration_seconds)
    if not success:
        agent_errors_total.labels(agent_name=agent_name).inc()


def record_sms(channel: str, *, success: bool) -> None:
    sms_sent_total.labels(channel=channel).inc()
    if not success:
        sms_failures_total.labels(channel=channel).inc()


def record_api_request(method: str, path: str, status_code: int, duration_seconds: float) -> None:
    api_request_seconds.labels(
        method=method, path=path, status=str(status_code),
    ).observe(duration_seconds)

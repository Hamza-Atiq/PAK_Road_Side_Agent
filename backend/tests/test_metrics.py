"""Unit tests for the Prometheus metrics layer."""
from __future__ import annotations

import pytest
from prometheus_client import generate_latest

from app.metrics import (
    agent_calls_total,
    agent_errors_total,
    api_request_seconds,
    celery_queue_length,
    celery_tasks_active,
    guardrail_blocks_total,
    incident_processing_seconds,
    incidents_assigned_total,
    incidents_created_total,
    incidents_escalated_total,
    incidents_no_provider_total,
    observe_incident_processing,
    provider_offline_detections_total,
    record_agent_call,
    record_api_request,
    record_sms,
    registry,
    sms_failures_total,
    sms_sent_total,
)


def test_all_required_metrics_exist_in_registry():
    """The Grafana dashboard depends on every metric being present in the
    custom registry. If someone removes one, this test catches it before deploy."""
    payload = generate_latest(registry).decode("utf-8")
    for name in [
        "incidents_created_total",
        "incidents_assigned_total",
        "incidents_no_provider_total",
        "incidents_escalated_total",
        "incident_processing_seconds",
        "agent_calls_total",
        "agent_errors_total",
        "agent_duration_seconds",
        "guardrail_blocks_total",
        "sms_sent_total",
        "sms_failures_total",
        "provider_offline_detections_total",
        "celery_tasks_active",
        "celery_queue_length",
        "api_request_seconds",
    ]:
        assert name in payload, f"missing metric: {name}"


def test_record_agent_call_success_only_bumps_calls():
    before_calls = agent_calls_total.labels(agent_name="UnitTestAgent")._value.get()
    before_errors = agent_errors_total.labels(agent_name="UnitTestAgent")._value.get()
    record_agent_call("UnitTestAgent", success=True, duration_seconds=0.123)
    assert agent_calls_total.labels(agent_name="UnitTestAgent")._value.get() == before_calls + 1
    # Errors counter must not move
    assert agent_errors_total.labels(agent_name="UnitTestAgent")._value.get() == before_errors


def test_record_agent_call_failure_bumps_both():
    before_calls = agent_calls_total.labels(agent_name="FailAgent")._value.get()
    before_errors = agent_errors_total.labels(agent_name="FailAgent")._value.get()
    record_agent_call("FailAgent", success=False, duration_seconds=0.5)
    assert agent_calls_total.labels(agent_name="FailAgent")._value.get() == before_calls + 1
    assert agent_errors_total.labels(agent_name="FailAgent")._value.get() == before_errors + 1


def test_record_sms_success_only_bumps_sent():
    before_sent = sms_sent_total.labels(channel="sms")._value.get()
    before_fail = sms_failures_total.labels(channel="sms")._value.get()
    record_sms("sms", success=True)
    assert sms_sent_total.labels(channel="sms")._value.get() == before_sent + 1
    assert sms_failures_total.labels(channel="sms")._value.get() == before_fail


def test_record_sms_failure_bumps_both():
    before_sent = sms_sent_total.labels(channel="whatsapp")._value.get()
    before_fail = sms_failures_total.labels(channel="whatsapp")._value.get()
    record_sms("whatsapp", success=False)
    assert sms_sent_total.labels(channel="whatsapp")._value.get() == before_sent + 1
    assert sms_failures_total.labels(channel="whatsapp")._value.get() == before_fail + 1


def test_observe_incident_processing_populates_histogram():
    observe_incident_processing(2.5)
    payload = generate_latest(registry).decode("utf-8")
    # The histogram emits buckets like incident_processing_seconds_bucket{le="5.0"} <count>
    assert "incident_processing_seconds_bucket" in payload
    assert "incident_processing_seconds_count" in payload


def test_record_api_request_uses_labels():
    record_api_request("GET", "/api/incidents/{incident_id}", 200, 0.05)
    payload = generate_latest(registry).decode("utf-8")
    assert 'path="/api/incidents/{incident_id}"' in payload
    assert 'status="200"' in payload


def test_counters_are_monotonic():
    """A counter must never decrease. Bumping should always increase the value."""
    before = incidents_created_total._value.get()
    incidents_created_total.inc()
    incidents_created_total.inc()
    after = incidents_created_total._value.get()
    assert after == before + 2


def test_gauge_can_go_up_and_down():
    """Gauges (active tasks) need to support both directions."""
    celery_tasks_active.labels(queue="test_q").inc()
    celery_tasks_active.labels(queue="test_q").inc()
    celery_tasks_active.labels(queue="test_q").dec()
    # Value should be net +1
    assert celery_tasks_active.labels(queue="test_q")._value.get() == 1.0


def test_metrics_payload_is_valid_prometheus_format():
    """The output must be parseable Prometheus exposition format."""
    payload = generate_latest(registry).decode("utf-8")
    # Each metric line starts with the metric name (no leading whitespace)
    # and contains '#' for HELP/TYPE lines.
    assert payload.startswith("#") or "_total" in payload
    assert "# HELP" in payload
    assert "# TYPE" in payload


def test_guardrail_blocks_counter_exists_and_increments():
    before = guardrail_blocks_total._value.get()
    guardrail_blocks_total.inc()
    assert guardrail_blocks_total._value.get() == before + 1


def test_no_default_registry_pollution():
    """Our metrics live on a custom registry. The default registry shouldn't
    contain them (which would cause double counting if /metrics scraped both)."""
    from prometheus_client import REGISTRY as DEFAULT_REGISTRY
    default_payload = generate_latest(DEFAULT_REGISTRY).decode("utf-8")
    # incidents_created_total is OUR metric; if it leaks to default registry,
    # we have a configuration bug
    assert "incidents_created_total" not in default_payload

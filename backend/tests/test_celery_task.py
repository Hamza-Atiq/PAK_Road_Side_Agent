"""Smoke tests for Celery task wiring (does not require a running broker)."""
from __future__ import annotations

import uuid

import pytest

from app.tasks.incident_tasks import (
    TRANSIENT_ERRORS,
    process_incident_task,
    send_retry_notification,
)
from celery_worker import celery_app


def test_celery_app_configured():
    assert celery_app.main == "roadside"
    assert celery_app.conf.task_acks_late is True
    assert celery_app.conf.task_reject_on_worker_lost is True
    assert celery_app.conf.task_max_retries == 3


def test_task_routes_registered():
    routes = celery_app.conf.task_routes
    assert "tasks.incident_tasks.process_incident_task" in routes
    assert routes["tasks.incident_tasks.process_incident_task"]["queue"] == "incidents"


def test_beat_schedule_present():
    schedule = celery_app.conf.beat_schedule
    assert "tracking-agent" in schedule
    assert schedule["tracking-agent"]["schedule"] == 60.0


def test_process_incident_task_is_celery_task():
    """The decorator should turn it into a Task with a `.delay()` API."""
    assert hasattr(process_incident_task, "delay")
    assert hasattr(process_incident_task, "apply_async")
    assert process_incident_task.name == "tasks.incident_tasks.process_incident_task"


def test_send_retry_notification_is_celery_task():
    assert hasattr(send_retry_notification, "delay")
    assert send_retry_notification.name == "tasks.incident_tasks.send_retry_notification"


def test_invalid_incident_id_raises_value_error():
    """Invalid UUID string should raise immediately, not silently retry."""
    with pytest.raises(ValueError, match="invalid incident_id"):
        # Call the underlying function directly (bypass Celery dispatch)
        process_incident_task.run("not-a-uuid")


def test_transient_errors_list_includes_network_errors():
    """Confirm that the retry-trigger list covers the expected transient types."""
    import httpx
    import sqlalchemy.exc as sa_exc

    assert httpx.RequestError in TRANSIENT_ERRORS
    assert sa_exc.OperationalError in TRANSIENT_ERRORS
    assert ConnectionError in TRANSIENT_ERRORS
    assert TimeoutError in TRANSIENT_ERRORS

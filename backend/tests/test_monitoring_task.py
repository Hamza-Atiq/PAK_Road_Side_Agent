"""Wiring tests for the monitoring Celery task (no broker needed)."""
from __future__ import annotations

import pytest

from app.tasks.monitoring_tasks import TRANSIENT_ERRORS, run_tracking_agent
from celery_worker import celery_app


def test_monitoring_task_registered():
    assert run_tracking_agent.name == "tasks.monitoring_tasks.run_tracking_agent"
    assert hasattr(run_tracking_agent, "delay")


def test_monitoring_task_routed_to_monitoring_queue():
    routes = celery_app.conf.task_routes
    route = routes.get("tasks.monitoring_tasks.run_tracking_agent")
    assert route is not None
    assert route["queue"] == "monitoring"


def test_monitoring_task_on_beat_schedule():
    schedule = celery_app.conf.beat_schedule
    assert "tracking-agent" in schedule
    assert schedule["tracking-agent"]["task"] == "tasks.monitoring_tasks.run_tracking_agent"
    assert schedule["tracking-agent"]["schedule"] == 60.0


def test_monitoring_transient_errors_include_db_and_network():
    import httpx
    import sqlalchemy.exc as sa_exc
    assert httpx.RequestError in TRANSIENT_ERRORS
    assert sa_exc.OperationalError in TRANSIENT_ERRORS
    assert ConnectionError in TRANSIENT_ERRORS

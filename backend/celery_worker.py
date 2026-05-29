"""Celery application entry point.

Run worker:
    celery -A celery_worker worker --loglevel=info --concurrency=4 -Q incidents,notifications,monitoring

Run beat (scheduler):
    celery -A celery_worker beat --loglevel=info

Design notes
------------
- The API enqueues work and returns immediately; Celery workers do the
  long-running agent orchestration off the request path.
- `task_acks_late=True` means a task is acked only after it finishes. If a
  worker crashes mid-run, the broker re-queues the task — at-least-once
  semantics. Our agent steps are idempotent (state-machine validations
  refuse invalid transitions), so a replay is safe.
- Beat is configured but the scheduled `run_tracking_agent` task is wired
  up in Phase 9 (TrackingAgent).
"""
from __future__ import annotations

import sys
from pathlib import Path

# Make `backend/` importable whether we run `celery -A celery_worker ...`
# from inside backend/ or from the repo root.
BACKEND_ROOT = Path(__file__).resolve().parent
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from celery import Celery  # noqa: E402
from celery.signals import setup_logging, task_postrun, task_prerun  # noqa: E402

from app.config import settings  # noqa: E402
from app.metrics import celery_queue_length, celery_tasks_active  # noqa: E402
from app.middleware.logging import configure_logging  # noqa: E402


celery_app = Celery("roadside")

celery_app.conf.update(
    broker_url=settings.CELERY_BROKER_URL,
    result_backend=settings.CELERY_RESULT_BACKEND,
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    # Eager-import task modules so @shared_task registrations are visible to
    # this app instance even when the worker uses `-A celery_worker` directly.
    imports=(
        "app.tasks.incident_tasks",
        "app.tasks.monitoring_tasks",
    ),
    # Reliability
    task_acks_late=True,
    task_reject_on_worker_lost=True,
    task_default_retry_delay=30,
    task_max_retries=3,
    worker_prefetch_multiplier=1,
    # Routing
    task_routes={
        "tasks.incident_tasks.process_incident_task": {"queue": "incidents"},
        "tasks.incident_tasks.send_retry_notification": {"queue": "notifications"},
        "tasks.monitoring_tasks.run_tracking_agent": {"queue": "monitoring"},
    },
    # Beat schedule — TrackingAgent (Phase 9) runs every 60s
    beat_schedule={
        "tracking-agent": {
            "task": "tasks.monitoring_tasks.run_tracking_agent",
            "schedule": 60.0,
            "options": {"queue": "monitoring"},
        },
    },
)


@setup_logging.connect
def _configure_celery_logging(**_) -> None:
    """Use the same structlog config inside Celery workers."""
    configure_logging()


# ----------------------------------------------------------------------
# Metric hooks
# ----------------------------------------------------------------------


def _queue_for(task_name: str) -> str:
    """Resolve which queue a task name routes to. Falls back to 'default'."""
    routes = celery_app.conf.task_routes or {}
    entry = routes.get(task_name)
    if isinstance(entry, dict):
        return entry.get("queue", "default")
    return "default"


@task_prerun.connect
def _on_task_prerun(task_id=None, task=None, **_) -> None:
    if task is None:
        return
    celery_tasks_active.labels(queue=_queue_for(task.name)).inc()


@task_postrun.connect
def _on_task_postrun(task_id=None, task=None, **_) -> None:
    if task is None:
        return
    try:
        celery_tasks_active.labels(queue=_queue_for(task.name)).dec()
    except ValueError:
        # Gauge can underflow if prerun signal was missed (e.g. crash) — clamp at 0
        pass


# Optional helper used by a Celery beat task or admin endpoint to refresh
# the gauge from Redis LLEN. We don't auto-schedule this — keep beat lean.
def update_queue_length_gauges() -> None:
    """Update celery_queue_length gauges by polling Redis directly."""
    try:
        from redis import Redis
        from urllib.parse import urlparse

        url = urlparse(settings.CELERY_BROKER_URL)
        r = Redis(host=url.hostname or "localhost", port=url.port or 6379,
                  db=int((url.path or "/0").lstrip("/") or 0))
        for queue in ("incidents", "notifications", "monitoring", "default"):
            length = r.llen(queue)
            celery_queue_length.labels(queue=queue).set(length)
    except Exception:  # noqa: BLE001 — metrics must never crash the worker
        pass

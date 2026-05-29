"""Celery tasks for periodic monitoring.

`run_tracking_agent` is scheduled by Celery beat every 60s (see
celery_worker.py beat_schedule). It opens a fresh async DB session,
runs the TrackingAgent scan, and returns a serializable summary that
Prometheus/Grafana can chart.
"""
from __future__ import annotations

import asyncio

import httpx
import sqlalchemy.exc as sa_exc
from celery import shared_task
from celery.utils.log import get_task_logger

from app.agents.base import AgentContext
from app.agents.tracking import TrackingAgent, TrackingScanResult
from app.database import AsyncSessionLocal, engine
from app.middleware.logging import get_logger
from app.models.enums import TaskLogStatus
from app.tools.db_write_tool import log_agent_step

celery_log = get_task_logger(__name__)
log = get_logger("tasks.monitoring")


TRANSIENT_ERRORS: tuple[type[Exception], ...] = (
    httpx.RequestError,
    httpx.TimeoutException,
    sa_exc.OperationalError,
    sa_exc.InterfaceError,
    ConnectionError,
    TimeoutError,
)


async def _run_tracking_scan() -> dict:
    """Open a session, run the scanner, log the summary.

    NB: every Celery tick runs in a fresh `asyncio.run()` loop. The module-scoped
    `engine` keeps a connection pool whose connections retain refs to futures
    from the previous loop, so we dispose at the end of each task. Without
    this, the next tick raises `RuntimeError: attached to a different loop`
    until the pool's pre-ping evicts the stale connection.
    """
    try:
        async with AsyncSessionLocal() as session:
            agent = TrackingAgent()
            ctx = AgentContext(db=session)
            try:
                result = await agent.run(ctx)
            except Exception:
                await session.rollback()
                raise

            outcome: TrackingScanResult | None = result.output
            summary = outcome.to_dict() if outcome else {"error": result.error}

            # Audit a single row so we can see the cadence and totals over time.
            try:
                await log_agent_step(
                    session,
                    incident_id=None,
                    agent_name="TrackingAgent",
                    step="tracking_scan",
                    status=TaskLogStatus.SUCCESS if result.success else TaskLogStatus.FAILURE,
                    payload=summary,
                    duration_ms=result.duration_ms,
                )
                await session.commit()
            except Exception:  # pragma: no cover — best-effort logging
                await session.rollback()

            return summary
    finally:
        await engine.dispose()


@shared_task(
    name="tasks.monitoring_tasks.run_tracking_agent",
    bind=True,
    autoretry_for=TRANSIENT_ERRORS,
    max_retries=2,
    retry_backoff=True,
)
def run_tracking_agent(self) -> dict:
    """Periodic scan task — fires every 60s via Celery beat."""
    celery_log.info("run_tracking_agent starting")
    try:
        summary = asyncio.run(_run_tracking_scan())
    except TRANSIENT_ERRORS as exc:
        celery_log.warning("transient error in tracking scan: %s", exc)
        raise
    except Exception as exc:
        celery_log.exception("permanent failure in tracking scan")
        # Don't retry — log and continue; next scheduled run will try again
        return {"error": str(exc)}

    celery_log.info("run_tracking_agent done: %s", summary)
    return summary

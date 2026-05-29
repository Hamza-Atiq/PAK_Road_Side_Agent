"""Celery tasks that drive incident processing.

The web API enqueues `process_incident_task(incident_id)` and returns
immediately. A Celery worker picks it up, opens a fresh async DB session,
and runs the OrchestratorAgent. Retries fire on transient errors only —
business outcomes like NO_PROVIDER are NOT retried.
"""
from __future__ import annotations

import asyncio
import uuid

from celery import shared_task
from celery.utils.log import get_task_logger

# Transient error types worth retrying. Permanent issues (validation, missing
# rows, guardrail blocks) raise different exception classes and skip retries.
import httpx
import sqlalchemy.exc as sa_exc

from app.agents.orchestrator import OrchestrationOutcome, process_incident
from app.database import AsyncSessionLocal, engine
from app.middleware.logging import get_logger
from app.models.enums import TaskLogStatus
from app.tools.db_write_tool import log_agent_step

celery_log = get_task_logger(__name__)
log = get_logger("tasks.incident")


TRANSIENT_ERRORS: tuple[type[Exception], ...] = (
    httpx.RequestError,
    httpx.TimeoutException,
    sa_exc.OperationalError,
    sa_exc.InterfaceError,
    ConnectionError,
    TimeoutError,
)


# ----------------------------------------------------------------------
# Async core
# ----------------------------------------------------------------------


async def _run_orchestrator(incident_uuid: uuid.UUID) -> dict:
    """Open a session, run the orchestrator, commit, return a serializable summary.

    NB: see monitoring_tasks._run_tracking_scan for why we dispose the engine
    at the end — each Celery tick is a fresh `asyncio.run()` loop and the
    pool would otherwise leak connections across loops.
    """
    try:
        async with AsyncSessionLocal() as session:
            try:
                # Audit-trail: task started
                await log_agent_step(
                    session,
                    incident_id=incident_uuid,
                    agent_name="CeleryTask",
                    step="process_incident_task.start",
                    status=TaskLogStatus.STARTED,
                )
                await session.commit()

                outcome: OrchestrationOutcome = await process_incident(
                    db=session, incident_id=incident_uuid
                )

                # Audit-trail: task ended
                await log_agent_step(
                    session,
                    incident_id=incident_uuid,
                    agent_name="CeleryTask",
                    step="process_incident_task.end",
                    status=TaskLogStatus.SUCCESS,
                    payload=outcome.to_dict(),
                )
                await session.commit()
                return outcome.to_dict()

            except Exception:
                await session.rollback()
                # Re-record the failure on a fresh session so the rollback above
                # doesn't lose the log entry.
                async with AsyncSessionLocal() as fresh:
                    try:
                        await log_agent_step(
                            fresh,
                            incident_id=incident_uuid,
                            agent_name="CeleryTask",
                            step="process_incident_task.error",
                            status=TaskLogStatus.FAILURE,
                        )
                        await fresh.commit()
                    except Exception:  # pragma: no cover — best-effort logging
                        pass
                raise
    finally:
        await engine.dispose()


# ----------------------------------------------------------------------
# Celery task wrapper
# ----------------------------------------------------------------------


@shared_task(
    name="tasks.incident_tasks.process_incident_task",
    bind=True,
    autoretry_for=TRANSIENT_ERRORS,
    retry_backoff=True,
    retry_backoff_max=300,
    retry_jitter=True,
    max_retries=3,
)
def process_incident_task(self, incident_id: str) -> dict:
    """Process one incident end-to-end through the agent pipeline.

    Idempotent: the state machine refuses invalid transitions, so a replay
    after a worker crash is safe — it'll either re-do the missing steps
    or no-op the already-completed ones.
    """
    try:
        incident_uuid = uuid.UUID(incident_id)
    except (ValueError, TypeError) as exc:
        log.error("invalid_incident_id", incident_id=incident_id)
        raise ValueError(f"invalid incident_id: {incident_id}") from exc

    celery_log.info("process_incident_task starting for %s", incident_uuid)

    try:
        result = asyncio.run(_run_orchestrator(incident_uuid))
    except TRANSIENT_ERRORS as exc:
        celery_log.warning("transient error (will retry): %s", exc)
        raise  # Celery autoretry kicks in
    except Exception as exc:
        celery_log.exception("permanent failure processing incident %s", incident_uuid)
        # Don't retry on permanent errors — surface to admin via task_logs row
        raise

    celery_log.info(
        "process_incident_task done for %s, final=%s",
        incident_uuid,
        result.get("final_status"),
    )
    return result


@shared_task(
    name="tasks.incident_tasks.send_retry_notification",
    bind=True,
    autoretry_for=TRANSIENT_ERRORS,
    max_retries=2,
    retry_backoff=True,
)
def send_retry_notification(self, message_id: str) -> dict:
    """Retry hook for messages whose Twilio delivery failed.

    Phase 7's webhook already handles the SMS→WhatsApp fallback synchronously.
    This task exists for any caller (e.g. EscalationAgent) that wants to defer
    the retry. Currently a thin stub; expanded in Phase 9.
    """
    celery_log.info("send_retry_notification stub called for %s", message_id)
    return {"message_id": message_id, "stub": True}

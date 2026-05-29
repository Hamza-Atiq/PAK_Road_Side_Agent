"""Incidents API.

POST /                — customer submits an incident (multipart with optional image/voice).
                        Enqueues a Celery task; returns immediately with the new id.
GET  /my              — customer's own incidents
GET  /assigned        — provider's current assigned incident(s)
GET  /                — admin: all incidents, paginated + filterable
GET  /{id}            — detail (owner-or-admin gated)
PUT  /{id}/status     — provider/admin status transition with WS + SMS side-effects
PUT  /{id}/close      — customer/admin terminal close
"""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import Annotated

from fastapi import (
    APIRouter,
    Depends,
    File,
    Form,
    HTTPException,
    Query,
    Request,
    UploadFile,
    status,
)
from slowapi import Limiter
from slowapi.util import get_remote_address
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.base import AgentContext
from app.agents.communication import CommunicationAgent
from app.config import settings
from app.database import get_db
from app.metrics import incidents_created_total
from app.middleware.auth import CurrentUser, require_role
from app.middleware.logging import get_logger
from app.models.enums import IncidentStatus, UserRole
from app.models.incident import Incident
from app.models.user import User
from app.schemas.incident import (
    CloseIncidentRequest,
    IncidentBrief,
    IncidentCreateResponse,
    IncidentListResponse,
    IncidentResponse,
    StatusUpdateRequest,
)
from app.services.file_service import UploadValidationError, save_uploaded_file
from app.tools.db_read_tool import get_incident, get_user
from app.tools.db_write_tool import DbWriteError, update_incident_status
from app.tools.notification_tool import broadcast_incident_event

from app.middleware.rate_limit import rate_limit

log = get_logger("api.incidents")
limiter = Limiter(key_func=get_remote_address)

router = APIRouter(prefix="/api/incidents", tags=["incidents"])


# ----------------------------------------------------------------------
# Status transitions a given role may request directly.
# Anything more nuanced (re-dispatch, NO_PROVIDER recovery) goes through
# the AdminAgent or EscalationAgent — not this endpoint.
# ----------------------------------------------------------------------
_PROVIDER_ALLOWED_TARGETS = {
    IncidentStatus.EN_ROUTE.value,
    IncidentStatus.ARRIVED.value,
    IncidentStatus.COMPLETED.value,
}


def _ensure_owner_or_admin(user: User, incident: Incident) -> None:
    if user.role == UserRole.admin.value:
        return
    if user.role == UserRole.customer.value and incident.customer_id == user.id:
        return
    if user.role == UserRole.provider.value and incident.provider_id == user.id:
        return
    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail="you do not have access to this incident",
    )


# ----------------------------------------------------------------------
# POST /  — Customer creates incident
# ----------------------------------------------------------------------


@router.post(
    "",
    response_model=IncidentCreateResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Submit a new incident (multipart form with optional image + voice)",
    dependencies=[Depends(require_role(UserRole.customer))],
)
@rate_limit(limiter, settings.RATE_LIMIT_INCIDENT)
async def create_incident(
    request: Request,
    user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
    lat: Annotated[float, Form(ge=-90.0, le=90.0)],
    lng: Annotated[float, Form(ge=-180.0, le=180.0)],
    description: Annotated[str | None, Form()] = None,
    address: Annotated[str | None, Form()] = None,
    image: Annotated[UploadFile | None, File()] = None,
    voice: Annotated[UploadFile | None, File()] = None,
) -> IncidentCreateResponse:
    """Create the incident row, persist any uploaded media, then enqueue the
    OrchestratorAgent via Celery so the agent pipeline runs off the request path.
    """
    image_url: str | None = None
    voice_url: str | None = None
    try:
        if image is not None and image.filename:
            image_url = await save_uploaded_file(image, kind="image")
        if voice is not None and voice.filename:
            voice_url = await save_uploaded_file(voice, kind="audio")
    except UploadValidationError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    incident = Incident(
        customer_id=user.id,
        lat=lat, lng=lng,
        address=address,
        description=description,
        image_url=image_url,
        voice_url=voice_url,
        status=IncidentStatus.REPORTED.value,
    )
    db.add(incident)
    await db.flush()
    incidents_created_total.inc()

    # Broadcast creation before enqueue so admin live map sees it instantly
    await broadcast_incident_event(
        incident_id=incident.id,
        event="INCIDENT_CREATED",
        data={"lat": float(lat), "lng": float(lng), "customer_id": str(user.id)},
    )

    # Enqueue Celery — import lazily so the API process doesn't fail if the
    # broker URL isn't reachable at boot.
    queued = False
    try:
        from app.tasks.incident_tasks import process_incident_task
        process_incident_task.delay(str(incident.id))
        queued = True
    except Exception as exc:  # noqa: BLE001
        log.warning("celery_enqueue_failed", incident_id=str(incident.id), error=str(exc))

    return IncidentCreateResponse(
        id=incident.id,
        status=incident.status,
        queued=queued,
        message="incident received" + ("" if queued else " (worker enqueue failed; check broker)"),
    )


# ----------------------------------------------------------------------
# GET /my  — customer's own incidents
# ----------------------------------------------------------------------


@router.get(
    "/my",
    response_model=IncidentListResponse,
    summary="List the current customer's incidents",
    dependencies=[Depends(require_role(UserRole.customer))],
)
async def my_incidents(
    user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
) -> IncidentListResponse:
    total = int(
        await db.scalar(
            select(func.count(Incident.id)).where(Incident.customer_id == user.id)
        ) or 0
    )
    rows = list((await db.execute(
        select(Incident)
        .where(Incident.customer_id == user.id)
        .order_by(Incident.created_at.desc())
        .limit(limit).offset(offset)
    )).scalars())
    return IncidentListResponse(
        total=total, limit=limit, offset=offset,
        items=[IncidentBrief.model_validate(i) for i in rows],
    )


# ----------------------------------------------------------------------
# GET /assigned  — provider's currently-assigned incidents
# ----------------------------------------------------------------------


@router.get(
    "/assigned",
    response_model=IncidentListResponse,
    summary="List incidents currently assigned to this provider",
    dependencies=[Depends(require_role(UserRole.provider))],
)
async def assigned_incidents(
    user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
    include_history: bool = Query(
        False,
        description="When true, also include COMPLETED/CLOSED jobs (provider history).",
    ),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
) -> IncidentListResponse:
    if include_history:
        # Provider history: every incident this provider ever worked on
        stmt = select(Incident).where(Incident.provider_id == user.id)
        total = int(await db.scalar(
            select(func.count(Incident.id)).where(Incident.provider_id == user.id)
        ) or 0)
        rows = list((await db.execute(
            stmt.order_by(Incident.created_at.desc()).limit(limit).offset(offset)
        )).scalars())
    else:
        # Active jobs only (default — what the dashboard polls)
        active_statuses = (
            IncidentStatus.ASSIGNED.value,
            IncidentStatus.EN_ROUTE.value,
            IncidentStatus.ARRIVED.value,
        )
        rows = list((await db.execute(
            select(Incident)
            .where(Incident.provider_id == user.id)
            .where(Incident.status.in_(active_statuses))
            .order_by(Incident.updated_at.desc())
        )).scalars())
        total = len(rows)
    return IncidentListResponse(
        total=total, limit=limit if include_history else len(rows), offset=offset,
        items=[IncidentBrief.model_validate(i) for i in rows],
    )


# ----------------------------------------------------------------------
# GET /  (admin)  — all incidents paginated
# ----------------------------------------------------------------------


@router.get(
    "",
    response_model=IncidentListResponse,
    summary="Admin: list all incidents with optional status filter",
    dependencies=[Depends(require_role(UserRole.admin))],
)
async def list_all_incidents(
    db: Annotated[AsyncSession, Depends(get_db)],
    status_filter: str | None = Query(default=None, alias="status"),
    limit: int = Query(25, ge=1, le=200),
    offset: int = Query(0, ge=0),
) -> IncidentListResponse:
    stmt_base = select(Incident)
    if status_filter:
        if status_filter not in {s.value for s in IncidentStatus}:
            raise HTTPException(status_code=400, detail=f"unknown status: {status_filter}")
        stmt_base = stmt_base.where(Incident.status == status_filter)

    total = int(await db.scalar(
        select(func.count(Incident.id)).select_from(stmt_base.subquery())
    ) or 0)
    rows = list((await db.execute(
        stmt_base.order_by(Incident.created_at.desc()).limit(limit).offset(offset)
    )).scalars())
    return IncidentListResponse(
        total=total, limit=limit, offset=offset,
        items=[IncidentBrief.model_validate(i) for i in rows],
    )


# ----------------------------------------------------------------------
# GET /{id}  — detail
# ----------------------------------------------------------------------


@router.get(
    "/{incident_id}",
    response_model=IncidentResponse,
    summary="Get one incident (owner or admin)",
)
async def incident_detail(
    incident_id: uuid.UUID,
    user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> IncidentResponse:
    incident = await get_incident(db, incident_id)
    if incident is None:
        raise HTTPException(status_code=404, detail="incident not found")
    _ensure_owner_or_admin(user, incident)
    return IncidentResponse.model_validate(incident)


# ----------------------------------------------------------------------
# PUT /{id}/status  — provider or admin transition
# ----------------------------------------------------------------------


@router.put(
    "/{incident_id}/status",
    response_model=IncidentResponse,
    summary="Transition incident status (provider for own job; admin freely)",
)
async def update_status(
    incident_id: uuid.UUID,
    payload: StatusUpdateRequest,
    user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> IncidentResponse:
    incident = await get_incident(db, incident_id)
    if incident is None:
        raise HTTPException(status_code=404, detail="incident not found")

    if user.role == UserRole.provider.value:
        if incident.provider_id != user.id:
            raise HTTPException(status_code=403, detail="not your job")
        if payload.new_status not in _PROVIDER_ALLOWED_TARGETS:
            raise HTTPException(
                status_code=403,
                detail=f"provider may only set: {sorted(_PROVIDER_ALLOWED_TARGETS)}",
            )
    elif user.role != UserRole.admin.value:
        raise HTTPException(status_code=403, detail="forbidden")

    try:
        new_enum = IncidentStatus(payload.new_status)
        await update_incident_status(
            db, incident_id=incident.id, new_status=new_enum, reason=payload.reason,
        )
    except DbWriteError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    # Broadcast + notify customer for milestone transitions
    await broadcast_incident_event(
        incident_id=incident.id,
        event="STATUS_CHANGED",
        agent="API",
        data={"status": payload.new_status, "by_role": user.role},
    )

    if payload.new_status in {
        IncidentStatus.EN_ROUTE.value,
        IncidentStatus.ARRIVED.value,
        IncidentStatus.COMPLETED.value,
    }:
        customer = await get_user(db, incident.customer_id)
        provider_user = (
            await get_user(db, incident.provider_id) if incident.provider_id else None
        )
        if customer is not None:
            event_key = {
                IncidentStatus.EN_ROUTE.value: "en_route",
                IncidentStatus.ARRIVED.value: "arrived",
                IncidentStatus.COMPLETED.value: "completed",
            }[payload.new_status]
            agent = CommunicationAgent()
            await agent.run(AgentContext(
                db=db, incident_id=incident.id,
                payload={
                    "event": event_key,
                    "to_phone": customer.phone,
                    "context_data": {
                        "provider_name": provider_user.name if provider_user else "Your provider",
                        "eta_minutes": incident.eta_minutes,
                        "address": incident.address,
                    },
                },
            ))

    await db.refresh(incident)
    return IncidentResponse.model_validate(incident)


# ----------------------------------------------------------------------
# PUT /{id}/close  — customer or admin terminal
# ----------------------------------------------------------------------


@router.put(
    "/{incident_id}/close",
    response_model=IncidentResponse,
    summary="Force-close an incident (customer or admin)",
)
async def close_incident(
    incident_id: uuid.UUID,
    payload: CloseIncidentRequest,
    user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> IncidentResponse:
    incident = await get_incident(db, incident_id)
    if incident is None:
        raise HTTPException(status_code=404, detail="incident not found")
    _ensure_owner_or_admin(user, incident)
    # Providers can't close jobs; protect against role drift via _ensure helper
    if user.role == UserRole.provider.value:
        raise HTTPException(status_code=403, detail="providers cannot close incidents")
    try:
        await update_incident_status(
            db, incident_id=incident.id,
            new_status=IncidentStatus.CLOSED,
            reason=payload.reason or f"closed by {user.role}",
        )
    except DbWriteError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    await broadcast_incident_event(
        incident_id=incident.id, event="STATUS_CHANGED", agent="API",
        data={"status": IncidentStatus.CLOSED.value, "by_role": user.role},
    )
    await db.refresh(incident)
    return IncidentResponse.model_validate(incident)

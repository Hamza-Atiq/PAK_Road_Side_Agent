"""Admin API — dashboard, manual notify, reassign, suspend, NL query.

All endpoints require admin JWT. Wraps the AdminAgent for the NL-query path
and reuses build_dashboard_payload for the dashboard endpoint so both views
stay consistent.
"""
from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.admin_agent import (
    AdminAgent,
    AdminAgentOutcome,
    build_dashboard_payload,
)
from app.agents.base import AgentContext
from app.agents.communication import CommunicationAgent
from app.database import get_db
from app.middleware.auth import CurrentUser, require_admin
from app.middleware.logging import get_logger
from app.models.enums import IncidentStatus
from app.models.provider import Provider
from app.models.user import User
from app.schemas.admin import (
    AdminQueryRequest,
    AdminQueryResponse,
    DashboardResponse,
    NotifyRequest,
    NotifyResponse,
    ReassignRequest,
    ReassignResponse,
    SuspendRequest,
)
from app.tools.db_read_tool import get_incident, get_provider

log = get_logger("api.admin")

router = APIRouter(
    prefix="/api/admin",
    tags=["admin"],
    dependencies=[Depends(require_admin)],
)


# ----------------------------------------------------------------------
# Dashboard
# ----------------------------------------------------------------------


@router.get(
    "/dashboard",
    response_model=DashboardResponse,
    summary="Aggregate platform stats for the admin landing page",
)
async def dashboard(
    db: Annotated[AsyncSession, Depends(get_db)],
) -> DashboardResponse:
    payload = await build_dashboard_payload(db)
    return DashboardResponse.model_validate(payload)


# ----------------------------------------------------------------------
# Manual notify
# ----------------------------------------------------------------------


@router.post(
    "/notify",
    response_model=NotifyResponse,
    summary="Send a manual SMS or WhatsApp to any phone number",
)
async def notify(
    request: Request,
    payload: NotifyRequest,
    user: CurrentUser,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> NotifyResponse:
    """Admin types a message; CommunicationAgent sends it with content_override."""
    agent = CommunicationAgent()
    ctx = AgentContext(
        db=db,
        incident_id=payload.incident_id,
        payload={
            "event": "custom",
            "to_phone": payload.to_phone,
            "channel": payload.channel,
            "content_override": payload.body,
            "context_data": {"sent_by_admin_id": str(user.id)},
        },
    )
    result = await agent.run(ctx)
    out = result.output
    if out is None or not out.sent:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=out.reason if out else (result.error or "send failed"),
        )
    return NotifyResponse(
        message_id=out.message_id,
        twilio_sid=out.twilio_sid,
        delivery_status="SENT",
    )


# ----------------------------------------------------------------------
# Natural-language query
# ----------------------------------------------------------------------


@router.post(
    "/query",
    response_model=AdminQueryResponse,
    summary="Ask the AdminAgent a question in plain English",
)
async def admin_query(
    payload: AdminQueryRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> AdminQueryResponse:
    agent = AdminAgent()
    ctx = AgentContext(db=db, payload={"query": payload.query})
    result = await agent.run(ctx)
    out: AdminAgentOutcome | None = result.output
    if out is None:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=result.error or "admin agent failed",
        )
    return AdminQueryResponse(
        intent=out.intent,
        summary=out.summary,
        data=out.data,
        actioned=out.actioned,
    )


# ----------------------------------------------------------------------
# Reassign incident
# ----------------------------------------------------------------------


@router.put(
    "/incidents/{incident_id}/reassign",
    response_model=ReassignResponse,
    summary="Reassign an incident — auto-pick a new provider or use a specific one",
)
async def reassign_incident(
    incident_id: uuid.UUID,
    payload: ReassignRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> ReassignResponse:
    incident = await get_incident(db, incident_id)
    if incident is None:
        raise HTTPException(status_code=404, detail="incident not found")

    agent = AdminAgent()
    intent_params: dict = {"incident_id": str(incident_id)}
    if payload.new_provider_id:
        intent_params["new_provider_id"] = str(payload.new_provider_id)

    # Call the handler directly — avoids relying on Claude classification
    result = await agent._reassign_incident(
        AgentContext(db=db, incident_id=incident_id, payload={}),
        intent_params,
    )
    if result.get("error"):
        raise HTTPException(status_code=400, detail=result["error"])

    await db.refresh(incident)
    return ReassignResponse(
        incident_id=incident.id,
        new_provider_id=uuid.UUID(result["new_provider_id"]) if result.get("new_provider_id") else None,
        new_provider_name=result.get("new_provider_name"),
        status=incident.status,
        notes=result.get("rationale") or result.get("reason") or "reassign processed",
    )


# ----------------------------------------------------------------------
# Suspend provider
# ----------------------------------------------------------------------


@router.put(
    "/providers/{provider_id}/suspend",
    status_code=200,
    summary="Suspend a provider account (sets is_active=False, is_available=False)",
)
async def suspend_provider(
    provider_id: uuid.UUID,
    payload: SuspendRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> dict:
    user = await db.get(User, provider_id)
    if user is None or user.role != "provider":
        raise HTTPException(status_code=404, detail="provider not found")
    provider = await db.get(Provider, provider_id)
    if provider is None:
        raise HTTPException(status_code=404, detail="provider profile not found")

    user.is_active = False
    provider.is_available = False
    await db.flush()
    log.info(
        "provider_suspended",
        provider_id=str(provider_id),
        reason=payload.reason or "admin",
    )
    return {
        "provider_id": str(provider_id),
        "suspended": True,
        "reason": payload.reason or "admin action",
    }


# ----------------------------------------------------------------------
# Approve provider
# ----------------------------------------------------------------------


@router.put(
    "/providers/{provider_id}/approve",
    status_code=200,
    summary="Approve a provider account (sets is_approved=True)",
)
async def approve_provider(
    provider_id: uuid.UUID,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> dict:
    provider = await db.get(Provider, provider_id)
    if provider is None:
        raise HTTPException(status_code=404, detail="provider profile not found")
    provider.is_approved = True
    await db.flush()
    log.info("provider_approved", provider_id=str(provider_id))
    return {"provider_id": str(provider_id), "approved": True}

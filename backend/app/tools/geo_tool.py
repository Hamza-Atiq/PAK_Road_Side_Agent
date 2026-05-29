"""Agent-facing geo tool — thin wrapper around `geo_service.find_nearest_providers`.

Why a wrapper: keeps the agent's tool surface stable even if the underlying
PostGIS query implementation changes, and lets us add observability/metrics
per tool call in one place.
"""
from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from app.middleware.logging import get_logger
from app.services.geo_service import (
    ProviderCandidate,
    find_nearest_providers,
    haversine_km,
)

log = get_logger("tools.geo")

__all__ = ["find_nearest_providers_tool", "haversine_km", "ProviderCandidate"]


async def find_nearest_providers_tool(
    db: AsyncSession,
    *,
    lat: float,
    lng: float,
    radius_km: float,
    service_type: str | None = None,
    limit: int = 10,
) -> list[ProviderCandidate]:
    """Return nearest available approved providers within `radius_km` of (lat,lng)."""
    candidates = await find_nearest_providers(
        db,
        lat=lat,
        lng=lng,
        radius_km=radius_km,
        service_type=service_type,
        limit=limit,
    )
    log.info(
        "geo_query",
        lat=lat,
        lng=lng,
        radius_km=radius_km,
        service_type=service_type,
        candidate_count=len(candidates),
    )
    return candidates

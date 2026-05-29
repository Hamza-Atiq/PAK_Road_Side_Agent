"""Routing tool — actual road distance + ETA from provider to incident.

Primary: OpenRouteService Directions API (free, global, OSM-based).
Fallback: Haversine straight-line × 1.4 road factor + assumed 40 km/h avg speed.
The fallback keeps DispatchAgent's ETA reasoning functional in dev without an
ORS key, and as a graceful degradation if ORS is rate-limited or down.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

import httpx

from app.config import settings
from app.middleware.logging import get_logger
from app.services.geo_service import haversine_km

log = get_logger("tools.routing")

# Average driving speed used by the fallback estimator (km/h).
FALLBACK_AVG_SPEED_KMH = 40.0
# Road distance is typically ~1.4x straight-line distance for driveable routes.
ROAD_FACTOR = 1.4


@dataclass
class RouteResult:
    distance_km: float
    duration_minutes: float
    polyline: list[tuple[float, float]] | None  # [(lng, lat), ...] or None for fallback
    source: Literal["ors", "haversine_fallback"]

    def to_dict(self) -> dict:
        return {
            "distance_km": round(self.distance_km, 3),
            "duration_minutes": round(self.duration_minutes, 1),
            "source": self.source,
            "polyline_points": len(self.polyline) if self.polyline else 0,
        }


class RoutingToolError(Exception):
    pass


# ----------------------------------------------------------------------
# OpenRouteService request
# ----------------------------------------------------------------------


async def _route_via_ors(
    from_lat: float, from_lng: float, to_lat: float, to_lng: float
) -> RouteResult:
    """Call ORS Directions API. Raises RoutingToolError on any HTTP/parse failure."""
    if not settings.ORS_API_KEY:
        raise RoutingToolError("ORS_API_KEY not configured")

    url = f"{settings.ORS_BASE_URL.rstrip('/')}/v2/directions/driving-car"
    params = {
        "api_key": settings.ORS_API_KEY,
        "start": f"{from_lng},{from_lat}",
        "end": f"{to_lng},{to_lat}",
    }

    async with httpx.AsyncClient(timeout=10.0) as client:
        try:
            resp = await client.get(url, params=params)
        except httpx.RequestError as exc:
            raise RoutingToolError(f"ORS request failed: {exc}") from exc

    if resp.status_code != 200:
        raise RoutingToolError(f"ORS HTTP {resp.status_code}: {resp.text[:200]}")

    try:
        data = resp.json()
        feature = data["features"][0]
        summary = feature["properties"]["summary"]
        # GeoJSON coordinates are [lng, lat] pairs
        coords = feature["geometry"]["coordinates"]
        polyline = [(float(c[0]), float(c[1])) for c in coords]
    except (KeyError, IndexError, ValueError, TypeError) as exc:
        raise RoutingToolError(f"ORS response malformed: {exc}") from exc

    return RouteResult(
        distance_km=float(summary["distance"]) / 1000.0,
        duration_minutes=float(summary["duration"]) / 60.0,
        polyline=polyline,
        source="ors",
    )


# ----------------------------------------------------------------------
# Haversine fallback
# ----------------------------------------------------------------------


def _route_via_fallback(
    from_lat: float, from_lng: float, to_lat: float, to_lng: float
) -> RouteResult:
    straight = haversine_km(from_lat, from_lng, to_lat, to_lng)
    road = straight * ROAD_FACTOR
    duration = (road / FALLBACK_AVG_SPEED_KMH) * 60.0
    return RouteResult(
        distance_km=road,
        duration_minutes=duration,
        polyline=None,
        source="haversine_fallback",
    )


# ----------------------------------------------------------------------
# Public entry point
# ----------------------------------------------------------------------


async def get_route(
    from_lat: float, from_lng: float, to_lat: float, to_lng: float
) -> RouteResult:
    """Return road distance + ETA from origin to destination.

    Prefers ORS Directions for accuracy. Falls back to Haversine-based
    estimate on any ORS error (and logs a warning so we know fallback fired).
    """
    if settings.ORS_API_KEY:
        try:
            return await _route_via_ors(from_lat, from_lng, to_lat, to_lng)
        except RoutingToolError as exc:
            log.warning("ors_failed_using_fallback", error=str(exc))
    else:
        log.debug("ors_key_missing_using_fallback")

    return _route_via_fallback(from_lat, from_lng, to_lat, to_lng)

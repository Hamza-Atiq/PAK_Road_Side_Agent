"""Geospatial queries — nearest-provider lookup via PostGIS.

The PostGIS `<->` operator with a GiST index on `providers.location` makes
the nearest-neighbor query an index scan: sub-50ms even with thousands of
providers. We hand-write the SQL because GeoAlchemy2's KNN helpers are
verbose and we want explicit control over the ordering and the projected
distance.
"""
from __future__ import annotations

import math
import uuid
from dataclasses import dataclass

from sqlalchemy import String, bindparam, text
from sqlalchemy.ext.asyncio import AsyncSession


# ----------------------------------------------------------------------
# Result type
# ----------------------------------------------------------------------


@dataclass
class ProviderCandidate:
    provider_id: uuid.UUID
    name: str
    phone: str
    service_type: str
    distance_km: float
    is_available: bool
    is_approved: bool
    total_jobs: int

    def to_dict(self) -> dict:
        return {
            "provider_id": str(self.provider_id),
            "name": self.name,
            "phone": self.phone,
            "service_type": self.service_type,
            "distance_km": round(self.distance_km, 3),
            "is_available": self.is_available,
            "is_approved": self.is_approved,
            "total_jobs": self.total_jobs,
        }


# ----------------------------------------------------------------------
# Haversine — provider-independent straight-line distance
# ----------------------------------------------------------------------


_EARTH_KM = 6371.0088


def haversine_km(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    """Great-circle distance in km. Used as a cheap ranking signal and for
    Haversine-based fallbacks when ORS is unavailable.
    """
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlam = math.radians(lng2 - lng1)
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlam / 2) ** 2
    return 2 * _EARTH_KM * math.asin(math.sqrt(a))


# ----------------------------------------------------------------------
# Nearest-provider query
# ----------------------------------------------------------------------


# The CTE ranks providers by spatial distance via the GiST KNN operator and
# then filters by availability + radius + (optional) service type.
_KNN_SQL = """
WITH ranked AS (
    SELECT
        p.id              AS provider_id,
        u.name            AS name,
        u.phone           AS phone,
        p.service_type    AS service_type,
        p.is_available    AS is_available,
        p.is_approved     AS is_approved,
        p.total_jobs      AS total_jobs,
        ST_Distance(
            p.location,
            ST_SetSRID(ST_MakePoint(:lng, :lat), 4326)::geography
        ) / 1000.0        AS distance_km
    FROM providers p
    JOIN users u ON u.id = p.id
    WHERE p.location IS NOT NULL
      AND p.is_available = TRUE
      AND p.is_approved  = TRUE
      AND u.is_active    = TRUE
      AND (:service_type IS NULL OR p.service_type = :service_type)
    ORDER BY p.location <-> ST_SetSRID(ST_MakePoint(:lng, :lat), 4326)::geography
    LIMIT :limit
)
SELECT * FROM ranked
WHERE distance_km <= :radius_km
ORDER BY distance_km ASC;
"""


async def find_nearest_providers(
    db: AsyncSession,
    *,
    lat: float,
    lng: float,
    radius_km: float,
    service_type: str | None = None,
    limit: int = 10,
) -> list[ProviderCandidate]:
    """Return up to `limit` available approved providers within `radius_km`,
    ordered ascending by spatial distance (GiST KNN).

    Pass `service_type` to filter to a single category (mechanic, tow_truck, etc.).
    A None service_type returns all categories.
    """
    if not (-90.0 <= lat <= 90.0) or not (-180.0 <= lng <= 180.0):
        raise ValueError(f"invalid coordinates: lat={lat}, lng={lng}")
    if radius_km <= 0:
        raise ValueError("radius_km must be positive")
    if limit <= 0:
        raise ValueError("limit must be positive")

    # Explicit type on service_type — when it's None, asyncpg can't infer the
    # parameter type from the `(:service_type IS NULL OR ...)` predicate alone
    # and raises AmbiguousParameterError. Pinning to String resolves it.
    stmt = text(_KNN_SQL).bindparams(
        bindparam("lat", value=lat),
        bindparam("lng", value=lng),
        bindparam("radius_km", value=radius_km),
        bindparam("service_type", value=service_type, type_=String),
        bindparam("limit", value=limit),
    )

    result = await db.execute(stmt)
    return [
        ProviderCandidate(
            provider_id=row.provider_id,
            name=row.name,
            phone=row.phone,
            service_type=row.service_type,
            distance_km=float(row.distance_km),
            is_available=row.is_available,
            is_approved=row.is_approved,
            total_jobs=row.total_jobs or 0,
        )
        for row in result
    ]

"""PostGIS geography corridor queries with explicit temporal bounds."""

import json
from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.pipeline.corridor import RouteSample, split_dateline


@dataclass(frozen=True)
class GeometryHealth:
    valid: bool
    reason: str


async def geometry_health(session: AsyncSession, geometry: dict) -> GeometryHealth:
    """Ask PostGIS whether a sourced geometry is safe for spatial predicates."""
    result = await session.execute(
        text("""
            SELECT ST_IsValid(shape), ST_IsValidReason(shape)
            FROM (SELECT ST_GeomFromGeoJSON(:geometry) AS shape) AS candidate
        """),
        {"geometry": json.dumps(geometry, separators=(",", ":"))},
    )
    valid, reason = result.one()
    return GeometryHealth(bool(valid), str(reason))


def corridor_geojson(samples: list[RouteSample]) -> str:
    return json.dumps(
        {"type": "MultiLineString", "coordinates": split_dateline(samples)}, separators=(",", ":")
    )


async def point_within_corridor(
    session: AsyncSession,
    samples: list[RouteSample],
    *,
    longitude: float,
    latitude: float,
    radius_m: float,
) -> bool:
    if radius_m < 0:
        raise ValueError("corridor radius must be nonnegative")
    value = await session.scalar(
        text("""
        SELECT ST_DWithin(
            ST_GeomFromGeoJSON(:route)::geography,
            ST_SetSRID(ST_MakePoint(:longitude, :latitude), 4326)::geography,
            :radius_m
        )
    """),
        {
            "route": corridor_geojson(samples),
            "longitude": longitude,
            "latitude": latitude,
            "radius_m": radius_m,
        },
    )
    return bool(value)


async def hazard_ids_in_corridor(
    session: AsyncSession,
    samples: list[RouteSample],
    *,
    radius_m: float,
    start_at: datetime,
    end_at: datetime,
) -> list[UUID]:
    if radius_m < 0 or start_at.utcoffset() is None or end_at.utcoffset() is None:
        raise ValueError("radius and timezone-aware travel window required")
    if end_at < start_at:
        raise ValueError("travel window ends before it starts")
    result = await session.execute(
        text("""
        SELECT id FROM integration.canonical_records
        WHERE record_type = 'disaster'
          AND geometry IS NOT NULL
          AND valid_at <= :end_at
          AND (
            payload_json ->> 'ends_at' IS NULL
            OR (payload_json ->> 'ends_at')::timestamptz >= :start_at
          )
          AND ST_DWithin(
            geometry::geography,
            ST_GeomFromGeoJSON(:route)::geography,
            :radius_m
          )
        ORDER BY id
    """),
        {
            "route": corridor_geojson(samples),
            "radius_m": radius_m,
            "start_at": start_at,
            "end_at": end_at,
        },
    )
    return list(result.scalars())

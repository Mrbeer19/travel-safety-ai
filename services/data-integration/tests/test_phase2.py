"""Phase 2 checks using the public USGS event captured by module 04.

Provenance: external-data/tests/fixtures/real-sanitized/usgs/significant_month.json,
USGS public domain, HTTP 200, captured 2026-09-19T07:45:38Z, event us7000ti1p.
Only timestamp/coordinates/magnitude/title are copied from that response.
"""

import copy
from datetime import UTC, datetime, timedelta, timezone

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

from app.pipeline.normalize import (
    canonicalize_value,
    convert_unit,
    field_paths,
    normalize_place,
    normalize_severity,
    transform_checksum,
    utc_time,
)
from app.repositories.canonical_repo import CanonicalRepository
from app.repositories.models import CanonicalRecord, Quarantine


def usgs_record() -> dict:
    return {
        "event_id": "us7000ti1p",
        "event_type": "EARTHQUAKE",
        "title": "M 6.5 - 169 km W of Nikolski, Alaska",
        "severity": "UNKNOWN",
        "geometry": {"type": "Point", "coordinates": [-171.3756, 52.8594]},
        "effective_at": "2026-09-17T14:19:52.210Z",
        "official": True,
        "magnitude": 6.5,
        "magnitude_unit": "Mw",
        "depth_km": 98.0,
        "quality": {"status": "FRESH"},
        "source": {
            "source_id": "usgs:us7000ti1p",
            "provider": "USGS",
            "provider_record_id": "us7000ti1p",
            "authority": "OFFICIAL",
            "source_url": "https://earthquake.usgs.gov/earthquakes/eventpage/us7000ti1p",
            "observed_at": "2026-09-17T14:19:52.210Z",
            "published_at": "2026-09-18T14:29:54.553Z",
            "fetched_at": "2026-09-19T07:45:38Z",
            "schema_version": "1.0.0",
        },
    }


def test_pure_transforms_preserve_null_and_zero() -> None:
    assert convert_unit(None, "mph", "kmh") is None
    assert convert_unit(0, "mph", "kmh") == 0
    assert convert_unit(32, "fahrenheit", "celsius") == 0
    assert normalize_place("  New   York  ") == "new york"
    assert normalize_severity("red") == "UNKNOWN"
    assert normalize_severity("SEVERE") == "SEVERE"
    nested = {"segments": [{"departure_time": datetime(2026, 1, 1, 7, tzinfo=timezone_bkk)}]}
    assert canonicalize_value(nested) == {"segments": [{"departure_time": "2026-01-01T00:00:00Z"}]}
    assert field_paths(nested) == ["segments.0.departure_time"]
    assert utc_time(datetime(2026, 1, 1, tzinfo=UTC)) == "2026-01-01T00:00:00Z"
    assert transform_checksum().startswith("sha256:")
    with pytest.raises(ValueError):
        utc_time(datetime(2026, 1, 1))


timezone_bkk = timezone(timedelta(hours=7))


@pytest.mark.parametrize(
    "field,value",
    [
        ("magnitude", float("nan")),
        ("effective_at", "2026-09-17T14:19:52"),
        ("geometry", {"type": "Point", "coordinates": [52.8594, -171.3756]}),
    ],
)
async def test_invalid_input_is_quarantined(
    isolated_database: str, field: str, value: object
) -> None:
    engine = create_async_engine(isolated_database)
    try:
        async with AsyncSession(engine, expire_on_commit=False) as session:
            payload = usgs_record()
            payload[field] = value
            assert await CanonicalRepository(session).ingest("disaster", payload) is None
            await session.commit()
            assert (await session.scalar(select(func.count()).select_from(Quarantine))) >= 1
    finally:
        await engine.dispose()


async def test_canonical_upsert_keeps_lineage_and_geometry(isolated_database: str) -> None:
    engine = create_async_engine(isolated_database)
    try:
        async with AsyncSession(engine, expire_on_commit=False) as session:
            repository = CanonicalRepository(session)
            first = await repository.ingest("disaster", usgs_record())
            second = await repository.ingest("disaster", copy.deepcopy(usgs_record()))
            await session.commit()
            assert first is not None and second is not None
            assert first.id == second.id
            assert first.payload_json["canonical_geometry"]["coordinates"] == [-171.3756, 52.8594]
            assert first.lineage_json["magnitude"]["source_id"] == "usgs:us7000ti1p"
            assert (await session.scalar(select(func.count()).select_from(CanonicalRecord))) == 1
    finally:
        await engine.dispose()

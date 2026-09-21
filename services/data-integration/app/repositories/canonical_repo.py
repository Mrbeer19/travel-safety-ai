"""Idempotent canonical input persistence and explicit quarantine."""

import hashlib
import json
from datetime import datetime
from uuid import uuid4

from geoalchemy2.elements import WKTElement
from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.canonical import GENERATED_MODELS, RECORD_MODELS, RecordModel
from app.pipeline.normalize import TRANSFORM_VERSION, geometry_of, normalize_record, record_sources
from app.repositories.models import CanonicalRecord, Quarantine
from app.repositories.snapshot_repo import canonical_hash


def _geometry_wkt(record: RecordModel) -> WKTElement | None:
    geometry = geometry_of(record)
    if geometry is None:
        return None
    points = geometry["coordinates"]
    if geometry["type"] == "Point":
        return WKTElement(f"POINT ({points[0]} {points[1]})", srid=4326)
    vertices = ", ".join(f"{lon} {lat}" for lon, lat in points)
    return WKTElement(f"LINESTRING ({vertices})", srid=4326)


class CanonicalRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def ingest(self, kind: str, raw: dict) -> CanonicalRecord | None:
        try:
            source_hash = canonical_hash(raw)
        except (TypeError, ValueError):
            # Hash invalid JSON representations for traceability; never store their raw body.
            encoded = json.dumps(raw, sort_keys=True, default=str, allow_nan=True)
            source_hash = "sha256:" + hashlib.sha256(encoded.encode()).hexdigest()
        try:
            GENERATED_MODELS[kind].model_validate(raw)
            record = RECORD_MODELS[kind].model_validate(raw)
            payload, lineage = normalize_record(record)
        except (KeyError, ValidationError, ValueError) as error:
            field_path = None
            if isinstance(error, ValidationError):
                field_path = ".".join(str(part) for part in error.errors()[0]["loc"])
            self.session.add(
                Quarantine(
                    source_hash=source_hash,
                    error_code="INVALID_INPUT",
                    field_path=field_path,
                    raw_content=None,
                )
            )
            await self.session.flush()
            return None
        content_hash = payload.pop("canonical_content_hash")
        source = record_sources(record)[0]
        valid_at: datetime | None = getattr(record, "valid_at", None)
        if valid_at is None:
            valid_at = getattr(record, "effective_at", None)
        key = {
            "record_type": kind,
            "source_id": source.source_id,
            "content_hash": content_hash,
        }
        await self.session.execute(
            insert(CanonicalRecord)
            .values(
                id=uuid4(),
                **key,
                schema_version=source.schema_version,
                transform_version=TRANSFORM_VERSION,
                payload_json=payload,
                lineage_json=lineage,
                geometry=_geometry_wkt(record),
                valid_at=valid_at,
                fetched_at=source.fetched_at,
            )
            .on_conflict_do_nothing(constraint="uq_canonical_version")
        )
        return (await self.session.execute(select(CanonicalRecord).filter_by(**key))).scalar_one()

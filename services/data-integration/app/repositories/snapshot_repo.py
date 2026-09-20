"""Immutable, idempotent snapshot persistence; pipeline is implemented later."""

import hashlib
import json
from uuid import UUID, uuid4

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.errors import SnapshotConflictError
from app.repositories.models import Snapshot


def canonical_hash(value: dict) -> str:
    encoded = json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False
    )
    return "sha256:" + hashlib.sha256(encoded.encode("utf-8")).hexdigest()


class SnapshotRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def create(
        self,
        *,
        request_id: UUID,
        input_content_hash: str,
        schema_version: str,
        evidence: dict,
        feature_schema_version: str | None = None,
        supersedes_id: UUID | None = None,
    ) -> Snapshot:
        payload_hash = canonical_hash(evidence)
        proposed_id = uuid4()
        statement = (
            insert(Snapshot)
            .values(
                id=proposed_id,
                request_id=request_id,
                input_content_hash=input_content_hash,
                content_hash=payload_hash,
                schema_version=schema_version,
                feature_schema_version=feature_schema_version,
                evidence_json=evidence,
                supersedes_id=supersedes_id,
            )
            .on_conflict_do_nothing(constraint="uq_snapshot_input")
            .returning(Snapshot.id)
        )
        await self.session.execute(statement)
        existing = (
            await self.session.execute(
                select(Snapshot).where(
                    Snapshot.request_id == request_id,
                    Snapshot.input_content_hash == input_content_hash,
                    Snapshot.schema_version == schema_version,
                )
            )
        ).scalar_one()
        if existing.content_hash != payload_hash:
            raise SnapshotConflictError("idempotency key refers to different immutable content")
        return existing

    async def get(self, snapshot_id: UUID) -> Snapshot | None:
        return await self.session.get(Snapshot, snapshot_id)

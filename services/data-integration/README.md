# Data Integration (module 05)

Phase 1 provides the internal FastAPI service, PostGIS storage, migrations, immutable snapshot repository and quarantine. It does not expose the snapshot endpoints yet: validation, normalization and route/time integration are later phases, so an empty success response would misrepresent current safety data.

## Run in Docker

```bash
docker compose -f compose.yaml -f compose.dev.yaml config --quiet
docker compose -f compose.yaml -f compose.dev.yaml --profile app up -d --build data-integration
docker compose -f compose.yaml -f compose.dev.yaml run --rm data-integration uv run pytest -q
docker compose -f compose.yaml -f compose.dev.yaml run --rm data-integration uv run ruff check app tests
```

The dev service runs `alembic upgrade head` before serving. Production deployment must run the same migration as an explicit job before readiness turns green. `/health/live` reports process liveness; `/health/ready` checks configured internal auth, the integration table and PostGIS. `/metrics` exports request latency/counts and quarantine counts. `/internal/v1/storage/status` requires `Authorization: Bearer <INTERNAL_SERVICE_TOKEN>` and queries the database.

Settings come from environment variables. `POSTGRES_HOST`, `POSTGRES_PORT`, `POSTGRES_DB`, `POSTGRES_USER`, `POSTGRES_PASSWORD` control storage. An absent `INTERNAL_SERVICE_TOKEN` fails closed. The service never loads or rewrites the repository `.env` itself; Compose supplies it.

`python -m app.repositories.retention` is the separate idempotent maintenance command for records older than `QUARANTINE_RETENTION_DAYS` (default 30). Deployers must schedule it; Phase 1 does not run destructive cleanup as part of request handling. Raw rejected payloads are stored only when the caller explicitly marks storage permitted.

Tests create their own temporary PostgreSQL database using `TEST_DATABASE_URL` and drop it after the suite. They run migrations against that database, verify PostGIS spatial SQL and index creation, exercise repository idempotency and quarantine retention, and test auth/health against real storage. No Docker socket is needed inside the test container.

## Phase 2 input boundary

`CanonicalRepository.ingest(kind, payload)` validates the module 04 record, quarantines invalid input with a source hash and field path, and stores a versioned canonical record with EPSG:4326 geometry and field lineage. The caller owns the transaction. Repeated identical input returns the same row. Provider measurements remain nullable; missing values are never replaced with zero. Time values, including nested segment times, are normalized to UTC. A source's original severity and label remain in the payload; unknown provider severity scales map to `UNKNOWN` in the additional canonical field.

The strict input models in `app/domain/canonical.py` currently mirror module 04's wire records. They are not generated from the shared output schema: the producer uses singular `source` on a raw route, while `route-candidate.schema.json` requires `sources[]` so stitched legs keep each provider's provenance. Using the shared generated `RouteCandidate` directly at this input boundary would reject current module 04 responses. This is an explicit contract gap, not an implicit rename.

**Versioned contract proposal:** define a `RawRouteCandidate` input schema for module 04's single-provider record in a new contract revision. Module 04 should test that its serialized route validates against that schema. Module 05 should test that its strict input accepts the same captured route and that its later stitched output validates against the existing `RouteCandidate` schema, mapping the raw `source` to one `sources[]` entry before adding any other legs. The contract owner must approve and generate the shared Python model before this module replaces its local input model. No schema or producer file is changed in this branch.

Current gaps: dedicated least-privilege PostgreSQL login provisioning requires the shared infrastructure owner; Compose currently supplies the existing `POSTGRES_USER`. The production image runs as a non-root user. The Phase 0 draft semantics and fixtures remain on `docs/05-phase0-data-semantics` until reviewed and merged; they are deliberately absent from this branch, which starts from `origin/main`.

**Resume 2026-09-20:** Work on `feat/05-normalization-lineage` (base: `feat/05-normalization-inputs`; Phase 1: `feat/05-postgis-foundation`). Both stacked diffs are under 400 lines; no push or main changes. Docker evidence: first slice 6 tests passed; Phase 2 13 tests passed, Ruff lint/format passed, production image built. Next: secure the versioned raw-route schema and producer test with the contract/module 04 owners, then generate the input model and rerun consumer parity tests before declaring Phase 2 complete.

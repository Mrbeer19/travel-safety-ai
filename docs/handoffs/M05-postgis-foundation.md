# M05 Phase 1: service and storage foundation handoff

## 1. Metadata

| Field | Value |
| --- | --- |
| Module/owner | 05 Data Integration |
| Issue/PR | Stacked PR on #39 (`contract/05-integration-input-records`) |
| Branch | `feat/05-postgis-foundation` |
| Base/final commit | Base `215c28e`; phase commits `29b5dd5`, `8482cd2` |
| Date/time | 2026-09-21 Asia/Bangkok |
| Reviewers | Platform/compose owner, database owner, module 03/06 consumers |
| Contract/version | `CONTRACT_VERSION=1.0.0`; no shared schema change |
| Docker image | `smart-travel-data-integration:runtime` built from `services/data-integration/Dockerfile` |

## 2. Executive summary

Phase 1 adds the runnable `data-integration` service: a FastAPI app with liveness, readiness, and an authenticated internal storage probe. It also adds PostGIS migrations for immutable snapshots, quarantine, and field lineage, plus Docker and compose wiring. Readiness reports `not_ready` when the internal token or storage is missing, so the service never presents itself as healthy without its dependencies. The phase has no provider data and no business endpoints.

## 3. Original responsibility and acceptance

- [x] FastAPI scaffold with health, metrics, and the shared error envelope: `app/main.py`, `app/api/`.
- [x] PostGIS foundation in the `integration` schema: migration `0001_integration_schema`.
- [x] Snapshots cannot be updated or deleted: migration `0002_snapshot_immutability` adds a trigger.
- [x] Quarantine repository with a retention window: `app/repositories/quarantine_repo.py`, `retention.py`.
- [x] Service runs in Docker with a healthcheck.

## 4. Behavior and flows

| Endpoint | Auth | Behavior |
| --- | --- | --- |
| `GET /health/live` | none | `{"status":"live"}` while the process runs |
| `GET /health/ready` | none | 503 `auth` when `INTERNAL_SERVICE_TOKEN` is unset; 503 `storage` when PostgreSQL or PostGIS cannot be queried; otherwise `ready` |
| `GET /internal/v1/storage/status` | internal token | Snapshot count, or 503 `DEPENDENCY_UNAVAILABLE` |
| `GET /metrics` | none | Prometheus request count and latency by route template |

The dev compose command runs `alembic upgrade head` before uvicorn.

## 5. Architecture and design

| Path | Role |
| --- | --- |
| `app/settings.py` | Environment settings; secrets are `SecretStr` |
| `app/api/deps.py`, `envelope.py`, `internal.py` | Token check, response envelope, routes |
| `app/repositories/db.py`, `models.py` | Async engine and SQLAlchemy models |
| `app/repositories/snapshot_repo.py`, `quarantine_repo.py`, `retention.py` | Persistence and retention |
| `app/migrations/versions/0001`, `0002` | Schema, indexes, immutability trigger |
| `app/observability/` | JSON logging, metrics, request context |

## 6. API and contract

No shared schema changes. `/internal/v1/storage/status` is an operational probe and not part of §5.3. The snapshot endpoints arrive in PR 7.

## 7. Database and storage

`0001` enables PostGIS and creates `integration.snapshots`, `integration.quarantine`, and `integration.field_lineage` with their indexes. `0002` adds `reject_snapshot_mutation`, which blocks UPDATE and DELETE on snapshots, so a refresh must write a new snapshot. Both migrations have downgrades. Tests run migrations against a fresh database on the compose PostgreSQL through `TEST_DATABASE_URL`.

## 8. Real data and provenance

This phase has no provider data. Tests use only generated row identifiers.

## 9. Configuration and Docker

Shared files touched: `compose.yaml` (service `data-integration`, profile `app`, healthcheck on `/health/live`) and `compose.dev.yaml` (port 8003, read-only source mounts, `TEST_DATABASE_URL`). The compose owner should review these files.

| Variable | Required | Secret | Default | Failure if missing |
| --- | --- | --- | --- | --- |
| `INTERNAL_SERVICE_TOKEN` | yes | yes | none | readiness 503 `auth`; internal routes reject |
| `POSTGRES_PASSWORD` | yes | yes | empty | readiness 503 `storage` |
| `POSTGRES_HOST/PORT/DB/USER` | no | no | compose defaults | readiness 503 `storage` |
| `QUARANTINE_RETENTION_DAYS` | no | no | 30 | n/a |

```bash
docker compose -f compose.yaml -f compose.dev.yaml build data-integration
docker compose -f compose.yaml -f compose.dev.yaml run --rm data-integration uv run pytest -q
docker compose -f compose.yaml -f compose.dev.yaml run --rm data-integration uv run ruff check app tests
docker compose -f compose.yaml -f compose.dev.yaml run --rm data-integration uv run ruff format --check app tests
```

## 10. Verification evidence

| Check | Actual result at `8482cd2` |
| --- | --- |
| Docker pytest | `6 passed in 2.27s` |
| Docker Ruff lint | `All checks passed!` |
| Docker Ruff format | `27 files already formatted` |

Tests (6): liveness plus fail-closed auth, readiness against the real database, fresh migration plus spatial index, quarantine withholding the raw body unless permitted, retention deleting only expired rows, and snapshot idempotency plus conflict.

Not covered by an automated test: migration downgrade, and the UPDATE/DELETE trigger from `0002`. Both are follow-up test work.

## 11. Known limitations

- There is no typecheck gate yet (#48).
- The size is over the 400-line guideline (about 1,100 changed lines, not counting `uv.lock`). Most of it is scaffold and migrations, which cannot be split usefully without leaving a PR that has no tests.

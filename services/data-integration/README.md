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

Current gaps: dedicated least-privilege PostgreSQL login provisioning requires the shared infrastructure owner; Compose currently supplies the existing `POSTGRES_USER`. The production image runs as a non-root user. The Phase 0 draft semantics and fixtures remain on `docs/05-phase0-data-semantics` until reviewed and merged; they are deliberately absent from this branch, which starts from `origin/main`.

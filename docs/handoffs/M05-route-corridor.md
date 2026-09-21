# M05 Phase 4: route corridor and spatial-temporal alignment handoff

## 1. Metadata

| Field | Value |
| --- | --- |
| Module/owner | 05 Data Integration |
| Issue/PR | Two stacked PRs: `feat/05-route-corridor`, then `feat/05-route-corridor-geometry` |
| Branch | `feat/05-route-corridor-geometry` stacked on `feat/05-route-corridor` |
| Base/final commit | Phase 3 report `83c3160`; phase commits `ad7d8cf`, `a74d6da`, `eb54cf7`, `5c67e7a`, `0504e8b` |
| Date/time | 2026-09-21 Asia/Bangkok |
| Reviewers | Module 06 consumer (corridor semantics), database owner (index) |
| Contract/version | Canonical v1; `CORRIDOR_VERSION=1.0.0`, `ALIGNMENT_VERSION=1.0.0` |
| Docker image | `smart-travel-data-integration:runtime`, built at each branch tip |

## 2. Executive summary

Phase 4 samples each route along the geodesic with ETAs. It queries PostGIS for hazards that fall within the corridor distance and the travel window, and aligns weather, disaster, and transport evidence to the route by position and time. Routes that cross the 180° meridian are split into short parts, so neither PostGIS nor the planar math wraps the wrong way around the globe. Evidence that does not match stays out with an explicit status and reason (`OUTSIDE_COVERAGE`, `STALE`, `UNAVAILABLE`), never a silent match.

## 3. Original responsibility and acceptance

- [x] Densify the route with bounded spacing and interpolated ETA: `app/pipeline/corridor.py`.
- [x] Corridor distance search with an explicit travel window on PostGIS geography: `app/pipeline/spatial.py`.
- [x] Weather matched to the nearest route sample within an ETA tolerance, with a coverage ratio: `align_weather`, `weather_coverage`.
- [x] Transport matched by trip, operator, service, stops, and time, never by city name alone: `align_transport`.
- [x] Dateline and polar cases checked against hand-computed golden cases.
- [x] Geography GiST index: migration `0005_canonical_geography_index`.

## 4. Behavior and flows

1. `sample_route` interpolates great-circle points no further apart than `max_spacing_m`, with each ETA proportional to distance.
2. `split_dateline` breaks the samples into parts at the 180° crossing; `corridor_geojson` emits a MultiLineString.
3. `hazard_ids_in_corridor` returns disaster rows that have `ST_DWithin` of the corridor on geography and overlap `[start_at, end_at]`.
4. `align_weather`/`align_disaster` project a point onto the nearest sample segment, interpolate the ETA, and then check distance, time, and source quality.
5. `geometry_health` asks PostGIS `ST_IsValid` before a sourced polygon is used.

## 5. Architecture and design

| Path | Role |
| --- | --- |
| `app/pipeline/corridor.py` | Pure geodesic sampling and dateline split |
| `app/pipeline/spatial.py` | PostGIS corridor, hazard join, geometry validity |
| `app/pipeline/alignment.py` | Pure ETA alignment for weather, disaster, and transport |
| `app/migrations/versions/0005_canonical_geography_index.py` | GiST index on `geometry::geography` |

## 6. API and contract

No external endpoint or shared schema changed. Corridor and alignment versions are constants, so later snapshots can record them.

## 7. Database and storage

`0005` adds `ix_canonical_geography`, a GiST index on `(geometry::geography)` of `integration.canonical_records`, so `ST_DWithin` on geography can use an index. The downgrade drops the index. `test_fresh_migration_and_spatial_index` checks that the index exists after upgrade.

## 8. Real data and provenance

Tests use module 04 captures: Open-Meteo Fiji pair (HTTP 200, 2026-09-20T14:43:47Z), the USGS Aleutian earthquake (HTTP 200), an openrouteservice route, and an MTA GTFS-RT status. Route lines and polygons around those coordinates are test-only geometries, named as such in each test docstring. No runtime fixture or live event is hard-coded.

## 9. Configuration and Docker

No new environment variables or secrets. Compose is unchanged from Phase 1.

```bash
docker compose -f compose.yaml -f compose.dev.yaml build data-integration
docker compose -f compose.yaml -f compose.dev.yaml run --rm data-integration uv run pytest -q
docker compose -f compose.yaml -f compose.dev.yaml run --rm data-integration uv run ruff check app tests
docker compose -f compose.yaml -f compose.dev.yaml run --rm data-integration uv run ruff format --check app tests
```

## 10. Verification evidence

| Check | `feat/05-route-corridor` (`a74d6da`) | `feat/05-route-corridor-geometry` (`0504e8b`) |
| --- | --- | --- |
| Docker pytest | `34 passed in 3.62s` | `39 passed in 3.83s` |
| Docker Ruff lint | `All checks passed!` | `All checks passed!` |
| Docker Ruff format | `42 files already formatted` | `45 files already formatted` |

Tests: bounded spacing and ETA on the captured ORS route; the Fiji dateline split; invalid parameter rejection; geography corridor across the dateline; hazard join requiring both distance and effective time; MultiPolygon validity and bow-tie self-intersection; high-latitude dateline distance in metres; weather alignment on both sides of the dateline; an event ending before the route ETA being excluded; transport requiring a linked trip, stops, and time.

## 11. Known limitations

- `align_disaster` assumes Point geometry and raises on Polygon and MultiPolygon (#45). Use `hazard_ids_in_corridor` for area events until this is fixed.
- The ETA is linear in distance. Provider segment speeds are not used yet.
- There is no load or EXPLAIN evidence yet for the corridor query at scale; that belongs to PR 8.

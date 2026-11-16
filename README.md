# Global Jobs Platform (Phase 1)

Production-oriented foundation for multi-country job aggregation: FastAPI API, MongoDB persistence, Redis health checks, and Docker Compose for local development.

## Quick start (Docker)

```bash
cp .env.example .env
# Edit .env and set strong passwords

docker compose build
docker compose up -d
curl http://127.0.0.1:8085/health/ready
```

## LinkedIn collector image (Phase 2B — Playwright, profile `collector`)

```powershell
# Build collector image (API image unchanged)
docker compose --profile collector build collector

# Chromium smoke test (local HTML fixture, no LinkedIn network)
docker compose --profile collector run --rm collector python -m app.cli.browser_smoke

# Offline LinkedIn HTML replay into test DB
docker compose --profile collector run --rm collector python -m app.cli.collect `
  --source linkedin --country DE --keyword "backend engineer" --max-jobs 2 `
  --mongo-db global_jobs_test --linkedin-offline-html /app/app/modules/collection/linkedin/fixtures

# Session utilities (never prints cookies)
docker compose --profile collector run --rm collector python -m app.cli.linkedin_session status
docker compose --profile collector run --rm collector python -m app.cli.linkedin_session prepare
docker compose --profile collector run --rm collector python -m app.cli.linkedin_session logout

# Host workstation (headed browser — not in Docker)
python -m venv .venv
.\.venv\Scripts\pip install -r requirements-collector.txt
.\.venv\Scripts\python -m playwright install chromium
.\.venv\Scripts\python -m app.cli.linkedin_session login
.\.venv\Scripts\python -m app.cli.linkedin_session install-docker
```

Live LinkedIn is **disabled by default**. Manual smoke requires `ALLOW_LIVE_LINKEDIN_COLLECTION=true`, a user-provided `storage_state.json` in the `linkedin_auth` volume, and **`--confirm-live`** on the collect CLI. Use `--mongo-db global_jobs_test` and `--max-jobs 2` for the first operator run. Interactive login inside headless Docker is not supported—authenticate on the host, copy state into the volume.

## Celery workers & Beat (Phase 2C — fixture sources only)

```powershell
# Build worker image and start API + data stores + worker + beat (no public worker ports)
docker compose build api
docker compose --profile celery build worker
docker compose up -d
docker compose --profile celery up -d worker beat

# Worker / queue operations (internal)
docker compose --profile celery exec worker python -m app.cli.celery_ops ping
docker compose --profile celery exec worker python -m app.cli.celery_ops stats
docker compose --profile celery exec worker python -m app.cli.celery_ops dispatch-once

# Stop scheduler safely (leave API/Mongo/Redis running)
docker compose stop beat worker
```

LinkedIn is **not** scheduled: `CELERY_ALLOW_LINKEDIN_TASKS=false` and `ALLOW_LIVE_LINKEDIN_COLLECTION=false` by default. Workers write to `CELERY_WORKER_MONGO_DB_NAME` (`global_jobs_test`). Run **only one** Beat container to avoid duplicate schedules.

## Data quality & monitoring (Phase 2D)

```powershell
# Operational snapshot (JSON, sanitized — uses test DB by default in worker config)
docker compose exec api python -m app.cli.collection_monitor --mongo-db global_jobs_test

# Safe schema backfill (dry-run default: copies country_code -> search_country_code only)
docker compose exec api python -m app.cli.migrate_jobs_schema --mongo-db global_jobs_test
docker compose exec api python -m app.cli.migrate_jobs_schema --mongo-db global_jobs_test --apply

# Optional internal API (set INTERNAL_OPS_TOKEN in .env)
# GET /internal/v1/monitoring/snapshot  Header: X-Internal-Ops-Token: <token>
# GET /internal/v1/monitoring/coverage   Header: X-Internal-Ops-Token: <token>
```

## Global coverage manifest (Phase 3D)

Canonical **40 countries × 50 keywords** (2,000 pairs) lives in `config/global_jobs_40_countries_50_keywords_manifest.json` and imports into `coverage_targets` (disabled by default). This is separate from Celery `collection_targets`.

```powershell
docker compose exec api python -m app.cli.coverage_import --audit-scheduler
docker compose exec api python -m app.cli.coverage_import --apply --audit-scheduler --mongo-db global_jobs_test
docker compose exec api python -m app.cli.coverage_report --mongo-db global_jobs_test
```

See [docs/PHASE_3D_COVERAGE.md](docs/PHASE_3D_COVERAGE.md).

## Worldwide coverage strategy (Phase 3E)

Market-search provider research, 40-country feasibility matrix, pilot design, and **`data_provenance`** monitoring (no live market-search collection). See [docs/PHASE_3E_STRATEGY.md](docs/PHASE_3E_STRATEGY.md).

```powershell
docker compose exec api python -m app.cli.migrate_job_provenance --mongo-db global_jobs_test
```

## LinkedIn collection (primary)

Canonical **40 countries × 50 keywords**; LinkedIn is the intended live source. See [docs/LINKEDIN_COLLECTION.md](docs/LINKEDIN_COLLECTION.md).

```powershell
docker compose exec api python -m app.cli.linkedin_progress --mongo-db global_jobs_test
```

## Market-search — Adzuna (optional; not required for core product)

See [docs/PHASE_3F_MARKET_SEARCH.md](docs/PHASE_3F_MARKET_SEARCH.md). Live API requires `ALLOW_LIVE_MARKET_SEARCH_COLLECTION`, credentials, and `--confirm-live`.

Job geography separates **`search_country_code`** (market searched) from **`country_code`** (resolved from `location_text`, nullable). Stale marking is operator-only (`JOB_STALE_AFTER_DAYS=0` disables automation).

## Fixture collection (Phase 2A, fictional data only)

```bash
docker compose exec api python -m app.cli.collect --source fixture --country DE --keyword "backend engineer" --max-jobs 5 --mongo-db global_jobs_test
docker compose exec api python -m app.cli.collect --source fixture --country DE --keyword "backend engineer" --dry-run
```

## Public job boards (Phase 3B — offline-first)

Adapters: **Greenhouse**, **Lever**, **Ashby** (`JobSourceAdapter` pipeline). Celery Beat does **not** schedule them. Live network requires `ALLOW_LIVE_PUBLIC_BOARD_COLLECTION=true` and `--confirm-live`. See [docs/PHASE_3B_SOURCES.md](docs/PHASE_3B_SOURCES.md) and the operator runbook [docs/PHASE_3B_1_LIVE_SMOKE.md](docs/PHASE_3B_1_LIVE_SMOKE.md).

**Production readiness (Phase 3C):** [docs/PHASE_3C_PRODUCTION_READINESS.md](docs/PHASE_3C_PRODUCTION_READINESS.md) · [docs/CONTABO_DEPLOYMENT_PREFLIGHT.md](docs/CONTABO_DEPLOYMENT_PREFLIGHT.md)

```bash
docker compose exec api python -m app.cli.collect --source greenhouse --board-site sample \
  --country US --keyword engineer --max-jobs 5 --mongo-db global_jobs_test \
  --public-board-offline /app/tests/fixtures/public_boards/greenhouse/sample.json
```

## Demo data (manual, non-production)

```bash
docker compose exec api python -m app.cli.seed_demo
```

Refuses to run in `APP_ENV=production` unless `ALLOW_DEMO_SEED=true`.

## API (Phase 3A — Flutter-ready)

| Method | Path | Description |
|--------|------|-------------|
| GET | `/health/live` | Liveness |
| GET | `/health/ready` | MongoDB + Redis readiness |
| GET | `/api/v1/jobs` | Paginated job summaries (no full description) |
| GET | `/api/v1/jobs/stats` | Public aggregate job statistics |
| GET | `/api/v1/jobs/{job_id}` | Full job detail |
| GET | `/api/v1/countries` | Active jobs by **actual** country vs **search market** |

### Country filtering semantics

| Parameter | Meaning |
|-----------|---------|
| `country_code` | Filters **`country_code`** only (verified/resolved job location). Does **not** include search-market-only rows. |
| `search_country_code` | Filters collection search market (`search_country_code`). |
| `country_unknown=true` | Jobs with unknown actual country (`country_code` null/missing). |

Legacy rows missing `search_country_code` may still appear in `country_code` responses via API fallback on read, but **listing filters do not conflate the two fields**.

### `GET /api/v1/jobs` query parameters

`page`, `page_size` (max 100), `country_code`, `search_country_code`, `country_unknown`, `q` (title/company regex), `source`, `employment_type`, `workplace_type`, `is_remote`, `status` (default `active`), `posted_within` (days), `sort` (`posted_at_desc` default).

Pagination response: `total`, `total_pages`, `has_next`, `has_previous`, `has_more` (alias).

```http
GET /api/v1/jobs?country_code=DE&page=1&page_size=20
GET /api/v1/jobs?search_country_code=US&q=engineer&is_remote=true
GET /api/v1/jobs/stats
GET /api/v1/countries
```

Errors: `{"success": false, "error": {"code": "...", "message": "..."}}` with HTTP 4xx.

Set `API_CORS_ORIGINS` (comma-separated) for Flutter web clients. Internal monitoring remains token-gated (`INTERNAL_OPS_TOKEN`, header `X-Internal-Ops-Token`).

## Tests

Unit tests run without infrastructure:

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
pytest
```

Integration tests (MongoDB + Redis on the Compose network; tests are bind-mounted, not baked into the API image):

```bash
docker compose up -d
docker compose run --rm -e RUN_INTEGRATION=1 -e MONGO_DB_NAME=global_jobs_test ^
  -v ./tests:/app/tests:ro -v ./pyproject.toml:/app/pyproject.toml:ro api pytest
```

```powershell
# Ruff in container (same mounts optional)
docker compose run --rm -v ./tests:/app/tests:ro api ruff check app tests
```

## Stop

```bash
docker compose stop
```

Do **not** use `docker compose down -v` unless you intend to delete database volumes.

## Phase 2 preparation

See `app/workers/__init__.py` for collection adapter and checkpoint interfaces. Celery workers will land in `app/workers/` in a later phase.

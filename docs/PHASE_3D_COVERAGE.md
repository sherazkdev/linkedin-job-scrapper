# Phase 3D — Global Job Coverage Alignment (40 × 50)

## Purpose

Canonical **target configuration** for 40 countries and 50 job categories (2,000 country–keyword pairs) is independent of:

- `collection_targets` (Celery scheduler rows)
- Real jobs in MongoDB

Configured coverage does **not** prove jobs exist or that any source is authorized to collect them.

## Manifest

- Path: `config/global_jobs_40_countries_50_keywords_manifest.json`
- Validated in code: 40 ISO alpha-2 countries, 50 keywords, 2,000 unique pairs
- Deterministic `target_id`: `{CC}:{slug-keyword}` (see `app/modules/coverage/manifest.py`)

## Data stores

| Collection | Role |
|------------|------|
| `coverage_targets` | Canonical 2,000 rows, **disabled by default**, `awaiting_approved_source` |
| `collection_targets` | Scheduler-eligible rows per **source** (fixture defaults only in beat) |
| `jobs` | Verified ingested jobs (`country_code` vs `search_country_code`) |

## CLI

Dry-run import (safe default):

```bash
python -m app.cli.coverage_import --audit-scheduler
```

Apply to test DB (never production without `ALLOW_COLLECTION_PRODUCTION_DB`):

```bash
python -m app.cli.coverage_import --apply --audit-scheduler
```

Coverage report:

```bash
python -m app.cli.coverage_report
```

## Internal API

`GET /internal/v1/monitoring/coverage` — requires `INTERNAL_OPS_TOKEN` header `X-Internal-Ops-Token`.

## Source capability summary

| Source | Global country×keyword | Scheduled by Beat | Live default |
|--------|------------------------|-------------------|--------------|
| fixture | Simulated | Yes | No |
| linkedin | Theoretical | No | No (offline) |
| greenhouse / lever / ashby | No (employer board) | No | Gated |
| demo | No | No | N/A |

Do not enqueue 2,000 live tasks. Scale via cooldowns, concurrency caps, per-provider queues, and explicit operator activation.

## Verdicts

- **TARGET CONFIGURATION VERIFIED** — manifest validates (and optionally 2,000 rows in `coverage_targets`)
- **REAL GLOBAL DATA COVERAGE VERIFIED** — only when authorized sources demonstrate jobs across required markets (not claimed in Phase 3D)
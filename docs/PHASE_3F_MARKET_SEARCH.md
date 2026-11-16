# Phase 3F — Adzuna integration (offline-first)

## Credentials (env only — never commit)

```env
ADZUNA_APP_ID=
ADZUNA_APP_KEY=
ALLOW_LIVE_MARKET_SEARCH_COLLECTION=false
MARKET_SEARCH_MAX_JOBS_PER_RUN=5
ADZUNA_MAX_PAGES_PER_RUN=2
```

Register at [developer.adzuna.com](https://developer.adzuna.com/overview). Review redistribution terms before exposing jobs on a public API.

## Supported countries

Only ISO codes listed in `ADZUNA_COUNTRY` (`app/modules/coverage/market_providers.py`) — **15** of **40** manifest markets. PK, AE, and others require Jooble/Careerjet or remain unsupported.

## Offline test (no network)

```powershell
docker compose exec api python -m app.cli.collect --source adzuna --country US `
  --keyword "Software Engineer" --max-jobs 5 --dry-run `
  --market-search-offline /app/tests/fixtures/market_search/adzuna/us_page1.json `
  --mongo-db global_jobs_test
```

## Operator-approved live one-shot (not run in Phase 3F)

```powershell
# Requires: ALLOW_LIVE_MARKET_SEARCH_COLLECTION=true, ADZUNA_APP_ID, ADZUNA_APP_KEY
docker compose exec api python -m app.cli.collect --source adzuna --country US `
  --keyword "Software Engineer" --max-jobs 5 --confirm-live `
  --mongo-db global_jobs_test
```

## Pilot targets

`config/adzuna_pilot_targets.json` — US/DE on Adzuna; PK/AE awaiting other providers.

## Rollback

- Disable `ALLOW_LIVE_MARKET_SEARCH_COLLECTION`.
- Delete test rows by `source=adzuna` on `global_jobs_test` only (operator discretion).
- No Celery schedule for market search (fixture-only beat unchanged).
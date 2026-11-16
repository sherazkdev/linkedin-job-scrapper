# Phase 3B.2 — Field policy & test-DB API verification

## Posting date rules (Greenhouse)

| Field | Stored as |
|-------|-----------|
| `first_published` | `posted_at` when present |
| `updated_at` | `source_updated_at` only — **never** copied to `posted_at` |
| Missing `first_published` | `posted_at = null`, metric `missing_posted_at` |

## Required vs optional (normalizer)

**Required (reject if missing):** `source_job_id`, `title`, `company`, valid HTTPS `job_url`, `search_country_code`.

**Optional / incomplete (persist when present):** `posted_at`, description body, resolved `country_code`, employment/workplace.

**Description policy:** No fabricated text. Empty `description` with `description_provided=false` when the source omits body text. Flutter clients should use `job_url` / detail flow when `description_provided` is false.

## Test database vs production API

| Component | Default DB | Notes |
|-----------|------------|--------|
| Docker `api` service | `global_jobs` from `.env` | Normal user traffic |
| Pytest + `RUN_INTEGRATION=1` | `global_jobs_test` via `conftest` | Same app code, isolated DB |
| `collect` CLI | Redirects to `global_jobs_test` unless production allowed |

### Verify test-DB jobs through the API (no production switch)

**Option A — pytest (recommended):**

```powershell
docker compose run --no-deps --rm `
  -e RUN_INTEGRATION=1 -e MONGO_DB_NAME=global_jobs_test `
  -v "${PWD}/tests:/app/tests:ro" -v "${PWD}/pyproject.toml:/app/pyproject.toml:ro" `
  api pytest tests/api/test_test_db_api_verification.py -q
```

**Option B — temporary API on test DB (does not change running `api` service):**

```powershell
docker compose run --rm -p 18085:8000 `
  -e MONGO_DB_NAME=global_jobs_test `
  api uvicorn app.main:app --host 0.0.0.0 --port 8000
```

Then: `curl.exe "http://127.0.0.1:18085/api/v1/jobs?source=greenhouse&page_size=5"`

Production container on `:8085` continues using `global_jobs`.

## Source job identity

`sourceJobId` = `{board_site}:{provider_id}` for Greenhouse/Lever/Ashby — unique per employer board, dedup key with `source`.
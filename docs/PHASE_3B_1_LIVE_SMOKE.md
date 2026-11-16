# Phase 3B.1 — Controlled Greenhouse live smoke (operator runbook)

## Preconditions (all required)

| Check | Expected |
|-------|----------|
| `ALLOW_LIVE_PUBLIC_BOARD_COLLECTION` | `true` in **API/worker `.env`** (then recreate `api`) |
| `ALLOW_LIVE_LINKEDIN_COLLECTION` | `false` |
| `CELERY_ALLOW_LINKEDIN_TASKS` | `false` |
| Celery Beat | Running **fixture-only** schedules (no public-board targets) |
| Database | **`global_jobs_test` only** |
| Board token | Operator chooses a **public** Greenhouse board token (from `https://boards.greenhouse.io/{token}`) |
| Job cap | `--max-jobs 5` (hard-capped further by `PUBLIC_BOARD_MAX_JOBS_PER_RUN`) |
| Acknowledgment | **`--confirm-live`** on the CLI |

## Operator approval checkpoint

Before running live HTTP:

1. Confirm the board token is an employer’s **public** Greenhouse job board (not a private token).
2. Confirm legal/product stance on aggregating that employer’s public postings.
3. Type the exact board token in the command below (replace `{BOARD_TOKEN}`).
4. Record run ID and `adapter_metrics` from CLI logs.

**No live request is performed by documentation or CI** — only an operator executing the command below.

## One-shot PowerShell command (Windows host)

```powershell
# 1) Enable gate in .env (do NOT commit):
#    ALLOW_LIVE_PUBLIC_BOARD_COLLECTION=true

docker compose up -d api

# 2) Operator replaces {BOARD_TOKEN} with approved public board, e.g. stripe, airbnb, etc.
docker compose exec api python -m app.cli.collect `
  --source greenhouse `
  --board-site {BOARD_TOKEN} `
  --country US `
  --keyword "*" `
  --confirm-live `
  --max-jobs 5 `
  --mongo-db global_jobs_test `
  --run-owner "ops-live-smoke-3b1"
```

## Post-run verification

```powershell
# Default API on :8085 reads global_jobs — NOT the test DB after collect.
# Use Phase 3B.2 isolated verification (pytest or port 18085) first.

# After pointing a test-only API at global_jobs_test (see docs/PHASE_3B_2.md):
curl.exe -s "http://127.0.0.1:18085/api/v1/jobs?source=greenhouse&page_size=5"
```

### Second run (duplicate check)

Re-run the **same command**. Expect `unchanged_count` or `updated_count` ↑, `created_count` ≈ 0.

## Quality signals (from CLI `adapter_metrics`)

- `valid_listings` — jobs handed to normalizer
- `incomplete_skipped` — missing description, posted date, or URL
- `keyword_rejected` — title filter
- `duplicate_skipped` — checkpoint IDs

## Rollback / safety

- Production DB `global_jobs` is **refused** by CLI unless `ALLOW_COLLECTION_PRODUCTION_DB=true`.
- To remove smoke docs: delete from test DB by `source=greenhouse` and `run_owner` if needed (operator SQL, not automated here).
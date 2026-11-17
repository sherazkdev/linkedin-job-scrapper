# Phase 3 — Worldwide Automatic LinkedIn Job Scheduling (Preparation)

**Status:** Code and tests prepared. **Beat and live LinkedIn collection remain OFF** until explicit operator approval.

## Audit summary

| Layer | Role |
|-------|------|
| **Manifest** | `config/global_jobs_40_countries_50_keywords_manifest.json` — **40** countries, **50** keywords, **2000** canonical pairs (validated in CI). |
| **Coverage DB** | `coverage_targets` materialized from manifest via `app/cli/coverage_import.py`; rows **disabled by default**. |
| **Scheduler DB** | `collection_targets` — only **explicitly enabled** rows are Beat-eligible. |
| **Beat** | `dispatch_collection_targets` every `CELERY_BEAT_DISPATCH_INTERVAL_SECONDS` (default **120s**). Profile `celery` in Compose — **not deployed** on VPS pilot. |
| **Dispatcher** | `app/workers/dispatcher.py` — max `CELERY_DISPATCH_MAX_PER_TICK` (default **1**), source allowlist, skips LinkedIn when `CELERY_ALLOW_LINKEDIN_TASKS=false`. |
| **Fair coverage** | `CELERY_DISPATCH_FAIR_COUNTRY_COVERAGE=true` → round-robin by country before repeat dispatch. |
| **Worker** | Queue `collection`, `worker_prefetch_multiplier=1`, late ack, time limits 540/600s. |
| **Gates** | `ALLOW_LIVE_LINKEDIN_COLLECTION`, `CELERY_ALLOW_LINKEDIN_TASKS`, per-target `enabled`, locks, `next_eligible_at`, LinkedIn auth failure **24h disable**. |
| **Dedup / 24h** | Unchanged adapter filters + persistence dedupe; pilot provenance preserved. |

## Per-target tracking (new)

On each run completion, `collection_targets` records:

- `last_run_collected_count`, `last_run_created_count`, `last_run_updated_count`, `last_run_rejected_count`
- `last_run_duration_seconds`, `last_run_run_id`
- Existing: `last_success_at`, `last_failure_at`, `last_run_at`, `last_error_summary`, `next_eligible_at`

Full run detail remains in `collection_runs`.

## Hard daily cap (live LinkedIn only)

`LINKEDIN_MAX_LIVE_RUNS_PER_24H=30` counts non-dry `collection_runs` for source `linkedin` with `started_at` in the rolling 24h window. When `ALLOW_LIVE_LINKEDIN_COLLECTION=true`, the dispatcher, worker runner, and `pilot-dispatch-once` refuse additional live runs once the cap is reached (`LinkedInCollectionError` / `skipped_linkedin_daily_cap`).

## Monitoring

| Signal | Where |
|--------|--------|
| Queue depth | `python -m app.cli.celery_ops ping` (JSON includes `queue_depth`) |
| Eligible backlog | Internal ops snapshot `collection.pending_eligible_targets` |
| Worker health | Worker container healthcheck → `celery_ops ping` |
| Recent failures | `collection.failed_runs_today`, run documents |
| Throughput model | `python -m app.cli.scheduling_ops` or ops snapshot `scheduling.throughput_estimate` |
| Coverage audit | Coverage report / `app/modules/coverage/report.py` |

## Queue and worker limits (recommended production wave)

| Setting | Value | Notes |
|---------|-------|--------|
| `CELERY_DISPATCH_MAX_PER_TICK` | **1** | Avoid queue spikes |
| `CELERY_BEAT_DISPATCH_INTERVAL_SECONDS` | **120** | ~30 dispatch opportunities/hour |
| `CELERY_TARGET_COOLDOWN_SECONDS` | **3600** | Max one success/hour/target |
| `CELERY_WORKER_CONCURRENCY` | **1** for LinkedIn | Playwright/memory; Compose default 2 OK for fixture-only |
| `CELERY_TASK_DEFAULT_QUEUE` | `collection` | Isolated from API |
| `CELERY_ALLOW_LINKEDIN_TASKS` | **false** until approval | Hard gate in dispatcher + worker |
| LinkedIn caps | Env adapter limits | No CAPTCHA bypass; auth failures pause 24h |

## Expected daily coverage (measured model)

Pilot timings: **~35s p50**, **~90s p90** per bounded run (1–5 jobs). Planning uses **60s/run** conservative.

With defaults (Beat 120s, dispatch 1/tick, cooldown 3600s, LinkedIn concurrency 1):

- **Scheduler ceiling:** ~**720** dispatches/day (Beat-limited); worker can finish ~**1440**/day — **not safe** for LinkedIn.
- **Recommended operational cap:** **~30 runs/day** (rate-limit / session hygiene; see `recommended_operational_runs_per_day` in waves JSON).
- **Per-target cooldown:** at most **~24** successful reruns/day on the **same** target (3600s cooldown).
- **Full 2000 manifest at recommended ops:** **~67 days** for one pass; **~2.8 days** at scheduler ceiling (do **not** use ceiling live).

Wave 1 (40 × `software engineer`): **~1.3 days** at 30 runs/day recommended ops.

CLI: `python -m app.cli.scheduling_ops`

Waves file: `config/linkedin_scheduling_waves.json`

## Staged rollout plan

1. **Wave 0 (current):** ≤5 pilot LinkedIn targets; Beat OFF; preserve `global_jobs_pilot` (10 jobs).
2. **Wave 1:** Enable **40** country-wide `software engineer` scheduler targets only; Beat ON with gates above; monitor 48h.
3. **Wave 2:** +5 keywords → **200** targets max.
4. **Wave 3:** 25 keywords → **1000** targets.
5. **Wave 4:** Full **2000** — only if error rate &lt;5%, no auth wall spikes, VPS resources stable.

**Do not** import-enable all `coverage_targets` in one step.

## Readiness criteria (before Beat + Wave ≥1)

- VPS `scripts/server_pytest_linkedin.sh` green on deployed SHA
- Pilot job count **≥10** unchanged unless intentional growth
- Redis queue depth **&lt;5** between ticks under dry dispatch test
- Operator runbook for LinkedIn session refresh documented
- Rollback rehearsed on staging flags (no DB drop)

## Rollback procedure

1. Set `ALLOW_LIVE_LINKEDIN_COLLECTION=false` and `CELERY_ALLOW_LINKEDIN_TASKS=false` on worker.
2. Stop Beat (`docker compose --profile celery stop beat` or remove profile).
3. Disable non-pilot `collection_targets` (`enabled=false` for LinkedIn).
4. Leave MongoDB (`global_jobs`, `global_jobs_pilot`) intact.
5. Optional: drain Redis `collection` queue after confirming no in-flight tasks.

## Restart recovery

- Beat re-reads schedule file volume; dispatcher is stateless.
- Duplicate dispatch: deterministic `task_id` per target; collision → skip (no double queue).
- Stale locks: `release_stale_lock` + lock TTL; orphaned runs reconciled in collector.

## Approval gate

**Recurring live worldwide collection requires explicit operator approval** with chosen wave id and max enabled target count.

Enable checklist (only after approval):

1. Materialize/enable targets for approved wave only.
2. Point worker at correct DB (`CELERY_WORKER_MONGO_DB_NAME`).
3. Set `CELERY_DISPATCH_SOURCE_ALLOWLIST=linkedin` if needed.
4. Set `CELERY_ALLOW_LINKEDIN_TASKS=true` and `ALLOW_LIVE_LINKEDIN_COLLECTION=true` **only on collection worker**.
5. Start Beat profile with same conservative env.

**Do not enable all 2000 targets.**
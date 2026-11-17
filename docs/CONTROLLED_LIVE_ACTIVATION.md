# Controlled live activation (requires explicit GO)

**Default:** NO-GO until operator approval. Beat OFF, live OFF, auto publication OFF.

## Pre-GO checklist

- [ ] `bash scripts/server_pytest_linkedin.sh` green on deployed SHA
- [ ] `bash scripts/server_production_monitor.sh` — API 200, production total stable
- [ ] Session refresh per `docs/LINKEDIN_SESSION_REFRESH.md`
- [ ] Auth failures = 0 on **one** approved manual pilot run
- [ ] `promote_pilot reconcile` — understand create/update/deprecate plan

## Proposed settings (Wave 1 resume — not active)

| Setting | Value |
|---------|--------|
| `LINKEDIN_MAX_LIVE_RUNS_PER_24H` | **30** |
| Worker concurrency | **1** |
| `dispatch_max_per_tick` | **1** |
| Beat interval | **120s** (conservative) |
| Enabled targets | **≤40**, single keyword `software engineer` |
| Observer | `server_wave1_observer.sh` — auth fail limit **3** |
| Production sync | **Manual or gated** `promote_pilot sync-apply` only |

## Activate collection (approval only)

```bash
# NOT run without explicit approval
bash scripts/server_wave1_preflight.sh
bash scripts/server_wave1_activate.sh
```

## Verify new jobs reach public API (after collection + approved sync)

1. Pilot: `curl -s http://127.0.0.1:18097/api/v1/jobs?...&sort=posted_at_desc`
2. `bash scripts/server_promotion_safety.sh`
3. Approved apply: `docker exec -e ALLOW_PILOT_TO_PRODUCTION_PROMOTION=true linkedin-scraper-api-pilot \
     python -m app.cli.promote_pilot sync-apply --backup evidence/promotion_backups/<latest>.json`
4. Public: `bash scripts/server_public_api_verify_promotion.sh`

## Automatic publication (future cron — still gated)

- Schedule **read-only** `server_production_monitor.sh` + `promote_pilot reconcile` (no apply).
- `sync-apply` only when `ALLOW_PILOT_TO_PRODUCTION_PROMOTION=true` for the invocation.
- Use `promotion_sync_lock` — overlapping apply refused.
- `deprecate-stale --dry-run` first; production deprecate only when pilot rows are **stale/closed/removed**, never for auth pause alone.

## Stop conditions

- ≥3 auth-class failures in observation window
- Daily cap reached
- Queue depth sustained &gt; 5
- Validation failures on `promote_pilot validate`
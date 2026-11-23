# LinkedIn session refresh (manual — no auth bypass)

## LinkedIn SERP checkpoints

Independent collection runs always start at SERP offset **0** (newest jobs). Pagination within one run may continue to page 1, 2, etc. Persisted `page_index` is reset after each run. Stored checkpoint does not reload `processed_ids` — job refresh uses Mongo `(source, sourceJobId)` upserts. Use `--ignore-checkpoint` to omit loading the checkpoint document entirely.

## When to use

- `linkedin:authentication_required` on collection runs
- Observer / Wave stop for auth failures
- `python -m app.cli.linkedin_session status` shows poor `offline_quality` (missing, corrupt, empty, or unlikely_authenticated)

## What failures mean

| State | Typical cause | Automated retry? |
|-------|----------------|------------------|
| `authentication_required` | Auth wall HTML, missing `storage_state.json`, empty cookies | **No** (`NON_RETRYABLE`) |
| `session_expired` | Empty session file | **No** |
| `verification_required` | LinkedIn challenge page | **No** — human must complete in browser |
| `rate_limited` | Too many requests | **No** — wait and reduce cap |

Detection is in `app/modules/collection/linkedin/parser.py` (`detect_page_state`) and `session.py` (`require_session`). **Do not** disable these checks.

## VPS verification (read-only)

```bash
cd /var/www/linkedin-job-scrapper
bash scripts/server_verify_session.sh
docker exec linkedin-scraper-worker-linkedin python -m app.cli.linkedin_session status
```

## Manual refresh workflow (operator)

1. **Stop live dispatch** (already OFF if Beat stopped): confirm no `linkedin-scraper-beat` container.
2. On a **trusted workstation**, sign in to LinkedIn in a supported browser with the service account.
3. Export Playwright storage state to `storage_state.json` (project session transfer tooling — `scripts/vps_session_transfer.py` when configured).
4. Copy into Docker volume `linkedin_scraper_linkedin_auth` at `/data/linkedin/storage_state.json` with correct ownership for `browseruser`/`workeruser`.
5. Re-run `server_verify_session.sh` and `python -m app.cli.linkedin_session status --json` — expect `offline_quality=likely_authenticated` (cookie count alone is not proof of access).
6. Optional one-shot online check (explicit consent): `status --verify-online --confirm-live-network`.
7. Run a **single** permitted pilot collect (`server_pilot_once.sh` pattern) — **only after explicit approval** to resume live collection.
8. If another `authentication_required` occurs, **do not** loop retries; stop and re-inspect session/challenge. Copy `session_epoch_at.json` to `evidence/wave1_observation/` after refresh to reset observer auth-fail windows.

## Wave 1 auth failure timeline (reference)

See `docs/PRODUCTION_AUTOMATION_ROLLOUT.md` — four failures (AE, CZ, DK, FI) after ~15 successful runs, consistent with session invalidation mid-wave, not CAPTCHA bypass attempts.

## Prohibited

- Scraping logged-out / authwall pages as if they were results
- CAPTCHA solvers, credential stuffing, or rate-limit evasion
- Resetting auth failure counters to hide problems
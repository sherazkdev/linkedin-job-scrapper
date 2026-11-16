# Test verification report

**Last run:** 2026-11-16 (Docker `api` image, `RUN_INTEGRATION=1`, app+tests bind mounts)

## Command

```powershell
docker compose run --no-deps --rm -e RUN_INTEGRATION=1 `
  -v "${PWD}/tests:/app/tests:ro" -v "${PWD}/app:/app/app:ro" -v "${PWD}/pyproject.toml:/app/pyproject.toml:ro" `
  api pytest tests/ -q
```

## Result

| Metric | Count |
|--------|------:|
| **PASSED** | **174** |
| **FAILED** | **0** |
| **SKIPPED** | **0** (full suite; offline unit tests skip when `RUN_INTEGRATION≠1` — not executed in this run) |

- **Ruff:** `All checks passed!` (`app`, `tests`, Docker `api` image with mounts)
- **Manifest:** `tests/coverage/test_manifest_validation.py` (40 countries × 50 keywords = 2,000 pairs)
- **Compose:** `docker compose config` and `docker compose -f compose.contabo-pilot.yaml config` — OK
- **Images:** `api`, `worker-linkedin` (`global-jobs-collector-worker`) build OK

## Fixes applied (prior 7 failures)

1. **`test_live_verified_only_filter` / `test_data_provenance_explicit_filter`** — `$and` query shape; `_provenance_in_query` helper.
2. **`test_collect_then_api_reads_test_db`** — force `MONGO_DB_NAME=global_jobs_test` when `RUN_INTEGRATION=1`; `get_settings.cache_clear()`.
3. **`test_running_in_container_*`** — assert detection matches `/.dockerenv` (host + container).
4. **`test_first_seen_preserved_on_update`**, **`test_cancellation_releases_lock_*`**, **`test_linkedin_offline_pipeline_persists_jobs`** — target lock/query legacy `search_location`; relative `posted_at` dedup via matching `source_posting_label`.

## Git / deploy prep

- Repository initialized locally; see `docs/SECURITY_GIT_AUDIT.md` and `docs/GITHUB_CONTABO_DEPLOY.md`.
- `.env` and session artifacts excluded via `.gitignore`.

## Not run / blocked

- **Live LinkedIn Playwright on Windows/WSL** — policy (use Linux pilot only).
- **Contabo SSH deploy** — operator-controlled.
- **Production Mongo index migration** — not applied without explicit approval.

## Re-run quick gate

```powershell
docker compose run --no-deps --rm -e RUN_INTEGRATION=1 `
  -v "${PWD}/tests:/app/tests:ro" -v "${PWD}/app:/app/app:ro" `
  api pytest tests/ -q
```
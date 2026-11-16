# Production Readiness Report

**Verdict:** `READY_FOR_ISOLATED_LINUX_PILOT` (not `PRODUCTION_READY`)

**Date:** 2026-11-16 (repository state)

## Release acceptance gates

| Gate | Status | Evidence |
|------|--------|----------|
| G1 API contract | **PASS** | `GET /api/v1/jobs`, health routes; OpenAPI via FastAPI; `live_verified_only` + `data_provenance` filters added |
| G2 Data validation / dedup | **PASS** (offline) | Keyword relevance, 24h recency, upsert `(source, sourceJobId)`; provenance on API |
| G3 Manifest 40×50 | **PASS** | `validate_manifest()` → 40 countries, 50 keywords, 2000 targets |
| G4 Offline Celery/collection | **PASS** | Worker fixture e2e, policy, LinkedIn parser/timing suites |
| G5 Scheduler safety | **PASS** (design) | `CELERY_DISPATCH_MAX_PER_TICK=1`, allowlist, locks, checkpoints; Beat **disabled** |
| G6 Docker compose | **PASS** | `worker-linkedin` `--pool=solo`, timeouts aligned, `compose.contabo-pilot.yaml` limits |
| G7 Prod data protected | **PASS** | Test DB isolation; no prod index migration without flag |
| G8 Linux deploy docs | **PASS** | `CONTABO_DEPLOYMENT_GUIDE.md`, `CONTABO_LINUX_PILOT.md` |
| G9 Celery live on Linux | **NOT RUN** | Windows/WSL live Celery failed; manual CLI succeeded historically |
| G10 Multi-run stability | **NOT RUN** | Requires Contabo |
| G11 Capacity monitoring | **PARTIAL** | `internal_ops` snapshot; throughput model below |

## Throughput model (conservative)

- **2,000** country×keyword logical targets (manifest).
- City-level targets multiply search count (not in the 2,000 base).
- **Sustainable default:** `CELERY_DISPATCH_MAX_PER_TICK=1`, worker concurrency **1**, cooldown **≥3600s** → ~**24 targets/day** per worker without overlap (upper bound, not a promise).
- Completing **2,000 searches in 24h** needs ~**1 every 43.2s** sustained — **not feasible** with one Playwright worker without massive parallelization (explicitly **not enabled**).

## Architecture (summary)

FastAPI → MongoDB (`jobs`, `collection_*`) ← JobCollector ← LinkedIn adapter (Playwright).

Celery Beat → Redis `collection` queue → `worker-linkedin` (solo) **or** slim `worker` (fixtures).

## City / checkpoint / lock identity

- Checkpoints: `(source, country_code, keyword, search_location)` — migration on flag `ALLOW_COLLECTION_TARGET_INDEX_MIGRATION`.
- Targets: same when migration enabled.
- Collection runs: now persist `search_location` on new runs; active-run guard still keyword-level (documented limitation).

## Failure taxonomy (LinkedIn)

`LinkedInFailureState` includes `js_probe_timeout` (selector timeout + `document.readyState` probe failed) vs `page_unresponsive` (other). Not equivalent to account block without session/verification signals.

## Windows restriction

**No further live Playwright on Windows/WSL.** Use Linux pilot per `CONTABO_LINUX_PILOT.md`.
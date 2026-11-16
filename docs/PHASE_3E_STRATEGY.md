# Phase 3E — Real Worldwide Job Coverage Strategy

**Status:** Design and platform hardening only — **no live market-search collection**, no API purchases, no VPS deploy.

## Step 1 — Current coverage (verified)

| Layer | Count (typical test DB) |
|-------|-------------------------|
| Configured manifest combinations | **2000/2000** |
| Materialized `coverage_targets` | 4 (integration mini rows) unless `--apply` |
| Source-supported coverage rows | **0** |
| Enabled coverage rows | **0** (default) |
| Approved runnable combinations | **0** |
| Scheduler `collection_targets` enabled | **4** fixture |
| Live API verified jobs (`data_provenance=live_api_verified`) | **≤5** (Grafana Greenhouse smoke) |
| Offline provider-shaped jobs | **1+** (e.g. `sample:*` Greenhouse fixture) |
| Synthetic fixture jobs | **hundreds** |
| Demo seed jobs | **72** |

Monitoring uses **`data_provenance`** — not `JobSource` alone. Run:

```powershell
docker compose exec api python -m app.cli.coverage_report --mongo-db global_jobs_test
docker compose exec api python -m app.cli.migrate_job_provenance --mongo-db global_jobs_test
```

## Step 2 — Market-search API research (documentation only)

### Adzuna ([developer.adzuna.com](https://developer.adzuna.com/overview))

| Criterion | Assessment |
|-----------|------------|
| Keyword search | Yes (`what`, `what_exclude`) |
| Country/location | Country in URL path; optional `where` |
| 40 manifest countries | **~19 verified** path slugs (US, GB, DE, …) — not all 40 |
| Posting-time filter | `max_days_old` / `days` style filters |
| Pagination | Page in path `/search/{page}` |
| Stable IDs | `id` per ad |
| Apply URL | `redirect_url` (outbound) |
| Redistribution | **Review Adzuna API terms** — affiliate/display rules apply |
| Cost | Free developer registration; third-party notes cite low monthly caps — **confirm in portal** |
| Production | `app_id` + `app_key`; rate limits per agreement |

### Jooble REST ([help.jooble.org](https://help.jooble.org/en/support/solutions/articles/60001448238-rest-api-documentation))

| Criterion | Assessment |
|-----------|------------|
| Keyword search | `keywords` (required) |
| Location | `location` + optional `radius` |
| 40 countries | **Per-country portal + API key** — broad but not automatic for all 40 |
| Posting filter | `updated` on jobs; no rich `max_days_old` in free doc |
| Pagination | `page`, `ResultOnPage` |
| Stable IDs | `id` |
| Apply URL | `link` |
| Redistribution | **Partner terms** — verify before public API |
| Cost | Free tier **~100 requests/day/key/country** (resets UTC) |
| Production | Separate key per regional domain |

### Careerjet Publisher API ([careerjet.com/partners/api](https://www.careerjet.com/partners/api))

| Criterion | Assessment |
|-----------|------------|
| Keyword search | `keywords` |
| Country | `locale_code` (`en_PK`, `de_DE`, …) |
| 40 countries | **Wide locale table** — most manifest countries have a locale; verify BH/NG/NO with publisher |
| Posting filter | `sort=date` |
| Pagination | `page` (1–10), `page_size` ≤ 100 |
| Stable IDs | Job `url` + site fields |
| Apply URL | `url` |
| Redistribution | **Publisher/affiliate agreement** — `user_ip` + `user_agent` required |
| Cost | Affiliate model — **no list price in public doc** |
| Production | Affiliate key |

### Other candidates (not integrated)

- **The Muse / USAJobs / EU EURES** — region-specific; not a single 40-country matrix.
- **LinkedIn** — no authorized global search API for this use case; live automation **out of scope**.

## Step 3 — 40-country matrix

Implemented in code: `app/modules/coverage/market_providers.py` (`build_country_capability_matrix()`).

Summary (documentation-level, not live-tested):

- **Countries with ≥1 documented market-search provider:** see `matrix_summary()` in coverage report.
- **Adzuna verified slugs:** 19 manifest ISO codes.
- **Careerjet locales:** majority of manifest countries; gaps possible (e.g. BH, EG) → `unsupported` or `unknown`.
- **Jooble portals:** strong in PK, AE, DE, US, EU, Asia — not all 40 without per-domain keys.
- **Every country:** `api_credentials_required`, `commercial_redistribution_not_approved` until legal sign-off.

## Step 4 — 2,000-target collection strategy

**Do not schedule all 2,000 targets at once.**

1. **Tier countries** by provider coverage (Adzuna → Careerjet → Jooble fallback).
2. **Budget per target per day:** 1 search request + up to 3 pages (caps ~30–50 jobs ingest/run).
3. **Deduplication:** canonical key `(provider, provider_job_id)` → maps to existing `(source, sourceJobId)` when adapter registered.
4. **Incremental:** checkpoints (`page`, `results_seen`, `query_hash`) in `collection_checkpoints`.
5. **Freshness:** `max_days_old` / `sort=date`; mark `stale` via existing lifecycle rules.
6. **429 backoff:** Redis cooldown flag per provider; Celery `retry_backoff_max=300`, jitter.
7. **Concurrency:** max **2–5** concurrent market-search tasks per provider; separate Celery queue per provider.
8. **Priority:** enabled pilot countries (PK, DE, US, AE) × 2 keywords first; long tail weekly.
9. **Failure isolation:** failed target → `collection_status=failed` on coverage row; beat skips until reset.
10. **Cost rough-order (pilot only, 4 countries × 2 keywords × 2 pages/day):**
    - Jooble: ~16 req/day (under free 100/key).
    - Adzuna: ~16 req/day (confirm portal cap).
    - Careerjet: ~16 req/day (affiliate limits TBD).

Full 2,000 targets at 1 req/day ≈ **2,000 API calls/day** — requires **paid tiers** and **multi-key** strategy; not viable on free Jooble alone.

## Step 5 — Adapter architecture

- Base: `MarketSearchJobSourceAdapter` in `app/modules/collection/adapters/market_search.py`.
- Reuses existing `JobCollector` → `JobNormalizer` → `JobPersistenceService` → `CollectionRunService`.
- New `JobSource` values (e.g. `adzuna`) **not added** until operator approves credentials and ToS.
- HTTP via existing allowlisted client pattern (Phase 3B).
- Provenance: `live_api_verified` only when `confirm-live` + live network + no offline fixture.

## Step 6 — Data provenance

| Value | Meaning |
|-------|---------|
| `synthetic_fixture` | Fixture adapter / Celery fixture |
| `demo_seed` | `seed_demo` CLI |
| `offline_provider_fixture` | Board/LinkedIn offline JSON or HTML |
| `live_api_verified` | Operator-confirmed live fetch (e.g. Grafana smoke) |
| `unknown` | Legacy rows — run `migrate_job_provenance` (dry-run default) |

## Step 7 — Controlled pilot (design only — **do not run without approval**)

| Market | Keywords (examples) | Primary provider (doc) | Fallback | DB |
|--------|---------------------|------------------------|----------|-----|
| PK | Software Engineer, Data Analyst | Jooble (`pk.jooble.org`) | Careerjet `en_PK` | `global_jobs_test` only |
| DE | Software Engineer, Data Analyst | Adzuna `de` | Careerjet `de_DE` / Jooble `de` | same |
| US | Software Engineer, Data Analyst | Adzuna `us` | Jooble / Careerjet `en_US` | same |
| AE | Software Engineer, Procurement Officer | Careerjet `en_AE` | Jooble `ae` | same |

**Gates before live pilot:**

1. Signed API/affiliate agreements and redistribution approval.
2. Credentials in secrets manager (not in repo).
3. `ALLOW_LIVE_MARKET_SEARCH_COLLECTION=true` (future flag) + `--confirm-live`.
4. Max **10 jobs** per target first run; manual review of `country_code` vs `search_country_code`.
5. No Celery beat scheduling until pilot sign-off.

**Success metrics:** ≥1 `live_api_verified` job per pilot country with resolvable `country_code` or explicit `unknown` + `location_text` preserved.

## Step 8 — Repository quality

See final CI section in Phase 3E handoff report (pytest + ruff + docker health).

## Verdicts

| Verdict | Phase 3E |
|---------|----------|
| **Market-search source feasibility documented** | Yes (with explicit gaps) |
| **Genuine worldwide job coverage** | **No** — pilot not executed |
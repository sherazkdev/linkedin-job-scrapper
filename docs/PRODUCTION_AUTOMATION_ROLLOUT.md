# Production automation readiness (plan — not enabled on VPS)

## Current baseline (post–Wave 1 publication)

| Store | Role | LinkedIn live-verified active |
|-------|------|-------------------------------|
| `global_jobs_pilot` | Collection + verification sandbox | 80 (preserved) |
| `global_jobs` | Public API (`linkedin-scraper-api`) | 80 (published batch `pilot-promo-20261117T080545Z-2a5101c8`) |

**Hard gates (unchanged until separate approval):**

- Celery Beat **OFF**
- `ALLOW_LIVE_LINKEDIN_COLLECTION=false`
- `ALLOW_PILOT_TO_PRODUCTION_PROMOTION=false` (except one-shot apply with explicit env)
- No scheduled auto-sync to production

---

## 1. Investigation: four `linkedin:authentication_required` failures

Evidence: `evidence/publication_readiness/audit_20261117T073619Z.json` and pilot `collection_runs` since `2026-11-17T06:30:30Z`.

| UTC start | `country_code` | `error_summary` | `run_id` |
|-----------|----------------|-----------------|----------|
| 06:36:42 | AE | `linkedin:authentication_required` | `12573890-2b37-43b3-824d-c9a345630bd2` |
| 06:46:42 | CZ | `linkedin:authentication_required` | `3bc4eddd-78be-4e14-a642-38186c41627c` |
| 06:50:43 | DK | `linkedin:authentication_required` | `589e8f68-4d75-4fb8-85e6-ac9038dff0f3` |
| 06:56:42 | FI | `linkedin:authentication_required` | `1de83b8e-e68a-43da-b89b-41230ee604d5` |

### Mechanism (no bypass)

Failures are **not** retried (`NON_RETRYABLE` in `app/modules/collection/linkedin/errors.py`). The collector records `error_summary` from `LinkedInCollectionError.state` (e.g. `linkedin:authentication_required`).

**Detection paths:**

1. **Empty / missing session file** — `LinkedInSessionStore.require_session()` → `authentication_required` (“no valid storage state”).
2. **HTML auth wall** — `detect_page_state()` in `parser.py` matches `authwall`, “sign in to linkedin”, login username field → `authentication_required`.
3. **Search page classifier** — `search_page_capture.classify_search_page` can surface the same states before parsing cards.

### Interpretation (Wave 1)

- Failures arrived **in Beat dispatch order** (~4 minutes apart), after **~15 successful** country runs and **30 rolling-24h** cap usage (including **11 pre–Wave 1** pilot runs).
- **AE** later has **1** verified job (an earlier run succeeded); the logged failure is a **subsequent** run for the same market, consistent with **session invalidation mid-wave**, not a code bypass attempt.
- Observer stopped the wave at **≥3 auth-class failures** (`scripts/server_wave1_observer.sh`) — correct guardrail.

### Remediation before resuming live collection (approval required)

1. **Human session refresh** on VPS (`server_verify_session.sh` / documented login flow) — not automated in this phase.
2. **Reduce concurrent market churn** — keep `dispatch_max_per_tick=1`, cap 30/day until auth failure rate &lt;5% over 24h (wave readiness).
3. **Separate auth vs session-empty** in observer metrics (optional follow-up).
4. **Do not** disable `detect_page_state` or scrape logged-out pages — prohibited.

---

## 2. Automated pilot → production workflow (design)

### Principles

| Principle | Implementation |
|-----------|----------------|
| Idempotent upsert | `(source, sourceJobId)` — `apply_promotion()` |
| Pilot preserved | Writes only to `global_jobs` |
| Gated apply | `ALLOW_PILOT_TO_PRODUCTION_PROMOTION=true` one-shot |
| Audit | `promotion_audit_batches` + per-entry `prior_production_document` |
| Backup | `promote_pilot backup` JSON on host `evidence/promotion_backups/` |
| Rollback | `promote_pilot rollback --batch-id … --backup …` |
| Ongoing sync plan | `promote_pilot reconcile` → `analyze_publication_sync()` |

### Planned operator sequence (future cron — dry-run first)

```bash
bash scripts/server_promotion_safety.sh          # stopped Beat, validate, dry-run, backup
docker exec … python -m app.cli.promote_pilot reconcile
docker exec … python -m app.cli.promote_pilot monitor
# After explicit approval window only:
# docker exec -e ALLOW_PILOT_TO_PRODUCTION_PROMOTION=true … promote_pilot apply --backup …
# docker exec -e ALLOW_…=true … promote_pilot deprecate-stale   # if reconcile shows deprecations
```

### Code map

| Module | Purpose |
|--------|---------|
| `app/modules/promotion/pilot_to_production.py` | Eligibility, apply, rollback, backup |
| `app/modules/promotion/publication_sync.py` | Reconcile plan, `apply_production_deprecations()` |
| `app/modules/promotion/monitoring.py` | Freshness, lag, failures, coverage |
| `app/cli/promote_pilot.py` | `reconcile`, `monitor`, `deprecate-stale` |

---

## 3. Updates, dedup, expiry

- **Dedup:** Enforced by unique `(source, sourceJobId)` on upsert; `validate` checks duplicate `sourceJobId` in pilot eligibility.
- **Updates:** Re-apply eligible pilot rows → `updated` outcome with production prior in audit.
- **Expiry / stale on public site:** Jobs in production but **not** in pilot `ELIGIBLE_QUERY` → `deprecate-stale` sets `status=stale`, `unpublish_reason=pilot_no_longer_eligible` (separate audit `type=deprecation`). **Not run automatically** in this phase.
- **Pilot-only expiry:** Set `status=stale` on pilot; job drops from eligibility and appears in `would_deprecate_ids` on reconcile.

---

## 4. Monitoring

```bash
bash scripts/server_publication_monitor.sh   # VPS read-only
python -m app.cli.promote_pilot monitor
```

**Metrics emitted:**

- Job freshness (pilot vs production counts, posted last 24h)
- Publication sync delta (`would_create`, `would_deprecate`, lag samples)
- Collection health (completed/failed/auth failures, enabled targets)
- Coverage by `search_country_code` (pilot)
- Last promotion / deprecation batch metadata

**Suggested alerts (external):**

- `pilot_vs_production_eligible_delta` &gt; 0 for &gt; 4h
- `auth_class_failures` spike ≥ 3 / 24h
- `failed_runs` / total &gt; 5%
- Public API `total` for `live_verified_only` drops without approved deprecation

---

## 5. Public API contract (integrators)

**Endpoint:** `GET https://jobsfinder.batteryanimation2.com/api/v1/jobs`

| Query param | Semantics |
|-------------|-----------|
| `search_country_code` | ISO-3166-1 alpha-2, **market searched** (recommended for Wave 1 jobs) |
| `country_code` | Job location country (often `null` for LinkedIn live jobs) |
| `source` | `linkedin` |
| `live_verified_only` | `true` → `data_provenance=live_api_verified` |
| `data_provenance` | Optional explicit filter |
| `posted_within` | Days (1–365), filters `posted_at >= now - N days` |
| `sort` | `posted_at_desc` (default recommended), `posted_at_asc`, `last_seen_desc`, `title_asc` |
| `page`, `page_size` | Pagination (`page_size` ≤ 100) |

**Envelope:** `{"success": true, "data": { "items": [...], "total", "page", "page_size", "total_pages", "has_next", "has_previous", "has_more" }}`

**Item fields:** See `JobSummaryResponse` in `app/modules/jobs/schemas/job.py`. Tests: `tests/api/test_jobs_list_contract.py`.

**Example (GB, recent):**

```http
GET /api/v1/jobs?source=linkedin&search_country_code=GB&live_verified_only=true&posted_within=7&sort=posted_at_desc&page_size=20
```

---

## 6. Capacity vs 40 × 50 manifest

Reference: `config/global_jobs_40_countries_50_keywords_manifest.json` — **2000** canonical country×keyword targets (40 countries, 50 keywords).

Planning numbers from `config/linkedin_scheduling_waves.json`:

| Parameter | Value |
|-----------|--------|
| Hard daily live run cap | **30** (`LINKEDIN_MAX_LIVE_RUNS_PER_24H`) |
| Conservative seconds/run | **60** |
| Max worker concurrency (recommended) | **1** |
| Jobs per successful run (Wave 1) | **≤5** |

### Throughput

| Scope | Targets | Min days @ 30 runs/day | Max jobs/day (if all succeed @ 5 jobs) |
|-------|---------|-------------------------|--------------------------------------|
| Wave 1 (done) | 40 × 1 keyword | 2 | 150 |
| Wave 2 (5 keywords × 40) | 200 | 7 | 150 |
| Half manifest (25 × 40) | 1000 | **34** | 150 |
| Full manifest (50 × 40) | **2000** | **67** | 150 |

**Reality check (Wave 1):** Only **19** runs in observation window → **16** markets with jobs; auth stop at run **~19**. Effective coverage **≪** theoretical cap until session stability improves.

**Conclusion:** Full manifest **cannot** stay fresh on a **single worker @ 30 runs/day** without either raising cap (LinkedIn risk), shortening run duration, or **multiple waves over months**. Automation should prioritize **freshness of published subset** over enumerating all 2000 pairs daily.

---

## 7. Tested offline pipeline

```bash
pytest tests/promotion/test_publication_sync_pipeline.py tests/promotion/test_pilot_to_production.py tests/api/test_jobs_list_contract.py
```

Covers: apply → reconcile → pilot stale → deprecate plan → `apply_production_deprecations` → monitoring metrics → lag detection.

---

## 8. Rollout plan (requires separate approval)

| Phase | What | Live scraping | Auto production write |
|-------|------|---------------|------------------------|
| **P0 (now)** | Monitor + reconcile cron, safety script on demand | OFF | OFF |
| **P1** | Scheduled **dry-run** + alert if `would_create`/`would_deprecate` &gt; 0 | OFF | OFF |
| **P2** | **Weekly** approved apply window + backup + public verify | OFF | Manual gated apply |
| **P3** | Session refresh + Beat **Wave 1-only** resume, observer tuned | Gated ON | OFF |
| **P4** | Pilot collection stable 7d → optional **deprecate-stale** after apply | Gated ON | Gated ON |
| **P5** | Wave 2+ manifest expansion | Per wave approval | Gated sync |

**Preconditions for P3+:** pytest green, auth failures &lt;5% / 24h, explicit session refresh, daily cap respected, no `observer_check` auto-stop loop without ops review.

---

## 9. Preservation guarantees

- Promotion **copies**; pilot rows **unchanged**.
- Rollback uses audit + backup; does not drop pilot.
- Deprecation only affects **production** rows no longer pilot-eligible.
- No `dropDatabase`, no Wave 2 enablement in this plan.
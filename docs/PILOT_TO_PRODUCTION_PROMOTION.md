# Pilot → production publication (design)

## Problem

Wave 1 writes to **`global_jobs_pilot`**. The public API container (`linkedin-scraper-api`) reads **`global_jobs`**, so HTTPS returns **zero** LinkedIn jobs until promotion.

## Safe options (no API DB swap)

| Approach | Risk |
|----------|------|
| **A. Promotion copy** (recommended) | Idempotent upsert by `(source, sourceJobId)` into `global_jobs`; pilot DB unchanged; API config unchanged |
| B. Point production API at pilot | Breaks production isolation; not approved |
| C. Dual-read API | Code change + coupling; defer |

## Pilot API (inspection)

```bash
bash scripts/server_pilot_api_up.sh
curl -s http://127.0.0.1:18097/api/v1/jobs?source=linkedin&live_verified_only=true
```

Container: `linkedin-scraper-api-pilot` — **127.0.0.1:18097 only**.

## Promotion CLI

```bash
python -m app.cli.promote_pilot preflight   # read-only
python -m app.cli.promote_pilot dry-run
python -m app.cli.promote_pilot backup
# APPLY only after explicit approval + env:
# ALLOW_PILOT_TO_PRODUCTION_PROMOTION=true
python -m app.cli.promote_pilot apply
python -m app.cli.promote_pilot rollback --batch-id <id> --backup evidence/promotion_backups/<file>.json
```

**Eligibility:** `source=linkedin`, `data_provenance=live_api_verified`, `status=active`, non-empty `sourceJobId` and `job_url`.

**Apply is disabled by default** (`ALLOW_PILOT_TO_PRODUCTION_PROMOTION=false`).

## Rollback

1. Audit document in `global_jobs.promotion_audit_batches` (includes `prior_production_document` per update)
2. **Created** rows: delete where `promotion_batch_id` matches
3. **Updated** rows: restore full **pre-promotion production** document from audit or `production_prior_documents` in backup JSON (not pilot-only fields)

## Safety script (VPS, no apply)

```bash
bash scripts/server_promotion_safety.sh
bash scripts/server_pytest_linkedin.sh
```

## Wave 1

Promotion does **not** stop Beat or observer. Does **not** enable Wave 2.
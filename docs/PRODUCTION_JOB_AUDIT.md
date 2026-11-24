# Production job count audit (415 → 419)

**Confirmed:** 2026-11-24 via `python -m app.cli.production_job_audit` on VPS `linkedin-scraper-api` (`global_jobs`).

## Totals

| Database | Total jobs | `source=integration_test` | Integration test subscribers/notifications |
|----------|------------|---------------------------|--------------------------------------------|
| Production `global_jobs` | **419** (419 active) | **0** | N/A |
| Pilot `global_jobs_pilot` | **419** | **0** | **0** subs / **0** notifs |

Synthetic UAT residue on pilot is **fully removed**.

## The four additional production records

These are the four newest rows by `first_seen_at` (all **inserts** from pilot collection on **2026-11-23**, promoted **2026-11-24**). None are alert/UAT synthetic data.

| `sourceJobId` | Title | `data_provenance` | `first_seen_at` (UTC) | `posted_at` (UTC) | `promoted_from_pilot_at` (UTC) | Batch |
|---------------|-------|-------------------|------------------------|-------------------|--------------------------------|-------|
| `4493597472` | Software Engineer | `live_api_verified` | 2026-11-23T11:56:13.014 | 2026-11-23T05:56:13.014 | 2026-11-24T05:30:43.501 | `pilot-promo-20261124T053042Z-99fb53ce` |
| `4492366915` | Senior AI/ML Software Engineer | `live_api_verified` | 2026-11-23T11:56:13.014 | 2026-11-23T06:56:13.014 | 2026-11-24T05:30:43.501 | same |
| `4493630462` | Principal Software Engineer - Gitlab Java | `live_api_verified` | 2026-11-23T11:56:13.013 | 2026-11-23T10:56:13.013 | 2026-11-24T05:30:43.501 | same |
| `4493763292` | Senior Software Developer | `live_api_verified` | 2026-11-23T11:56:12.947 | 2026-11-23T11:00:12.947 | 2026-11-24T05:30:43.501 | same |

- **Source:** `linkedin` for all four.
- **Country:** `PK` on all four.
- **Creation history:** Pilot `first_seen_at` ~11:56 UTC on 2026-11-23; production net-new via promotion (preserved pilot `first_seen_at` on insert).

## Collection runs and promotion audits

| Signal | Observation |
|--------|-------------|
| `production_recent_collection_runs` | **Empty** — no recent LinkedIn collection writes on production |
| Promotion batch `pilot-promo-20261124T053042Z-99fb53ce` | All four jobs share this `promotion_batch_id` / `promoted_from_pilot_at` |
| Alerts UAT | `production_integration_test_source = 0`; pilot integration jobs/subs = 0 |

## Provenance conclusion

The **+4** count increase is from **authorized pilot → production promotion** (`apply_promotion` inserts for jobs that did not yet exist in production), not from:

- Alert processor / synthetic `integration_test` jobs
- Direct production LinkedIn collection (no recent `collection_runs`)
- Unaudited manual DB edits (promotion metadata present on all four)

**No records were deleted, modified, or backfilled** during this audit.

## Promotion batch ledger

Re-run the CLI includes `production_newest_promotion_batch_detail` for batch `pilot-promo-20261124T053042Z-99fb53ce` (`created_count` / `updated_count` from `promotion_audit_batches`).

## Re-run

```bash
cd /var/www/linkedin-job-scrapper && git pull
docker exec linkedin-scraper-api python -m app.cli.production_job_audit
```

Or upload `scripts/_vps_prod_audit_api.sh` via `scripts/vps_upload_run.py`.
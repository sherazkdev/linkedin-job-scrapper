# Production job count audit (415 → 419)

## Method

Read-only CLI: `python -m app.cli.production_job_audit` (production container, `global_jobs`).

On VPS:

```bash
docker cp /var/www/linkedin-job-scrapper/app/cli/production_job_audit.py linkedin-scraper-api:/tmp/production_job_audit.py
docker exec linkedin-scraper-api python /tmp/production_job_audit.py
```

## Findings

| Check | Result |
|-------|--------|
| `source=integration_test` in production | **Expected 0** (UAT synthetic source is pilot-only) |
| Pilot synthetic residue after cleanup | **0** jobs / **0** integration subscribers (post-`alerts_cleanup`) |
| Increment vs baseline 415 | **+4** active documents observed during deploy verification |

## Provenance assessment

The +4 increase is **not** from the alerts UAT CLI (synthetic jobs use `integration_test` and pilot DB only).

Most likely explanations (confirm with `production_job_audit` newest `first_seen_at` rows):

1. **Authorized pilot→production promotion** or publication sync inserting net-new `source`/`sourceJobId` pairs.
2. **Lifecycle / reactivation** adding jobs previously outside the active public count (less common for a +4 step).

**No records were modified** in this audit phase.

## Uncertainty

Until `production_newest` JSON is captured from the CLI on a host with the committed audit module, exact `sourceJobId` values for all four rows are **not fixed in this document** — run the CLI after pulling commit containing `app/cli/production_job_audit.py`.
# Collection integration deploy (LinkedIn only)

## Throughput expectations (corrected)

With **30 live runs/day** and up to **15 jobs/run**, the theoretical upper bound is **450 fetched records per day** before deduplication, relevance rejection, and duplicate handling. **300–500 new unique jobs/day is a goal, not a guarantee.**

## Compose usage (VPS)

Always use the **full stack** of files — do not deploy with a single override in isolation:

```bash
cd /var/www/linkedin-job-scrapper
COMPOSE="docker compose -f compose.yaml -f compose.contabo-vps.yaml -f compose.contabo-wave1.yaml -p linkedin-scraper"
```

**Do not** run `docker volume prune`, `down -v`, or other destructive volume operations in production.

## Wave 1 activation (when auth is restored and operator approves)

Do **not** activate while LinkedIn reports authentication/verification failures.

```bash
export WAVE1_ENABLE_GROUP=software_core      # or software_expanded_10, etc.
export WAVE1_MAX_JOBS_PER_RUN=10             # optional; capped by worker env
bash scripts/server_wave1_activate.sh
```

Activation uses `wave1_ops enable-group` and writes `evidence/wave1_observation/wave1_activation.json`.

After manual session refresh, reset auth counting:

```bash
date -u +%Y-%m-%dT%H:%M:%SZ | xargs -I{} printf '{"session_epoch_at":"{}"}\n' > evidence/wave1_observation/session_epoch_at.json
```

## Job expiry (daily)

Dry-run (default in CLI; cron uses apply when enabled):

```bash
ALLOW_SCHEDULED_JOB_EXPIRY=true JOB_EXPIRY_APPLY=false bash scripts/server_job_expiry_scheduled.sh
```

Apply (marks `status=expired`, no deletes):

```bash
ALLOW_SCHEDULED_JOB_EXPIRY=true JOB_EXPIRY_APPLY=true bash scripts/server_job_expiry_scheduled.sh
```

## Pilot→production lifecycle propagation

Preview only:

```bash
docker exec linkedin-scraper-api-pilot python -m app.cli.promote_pilot lifecycle-preview
```

Scheduled (deprecate only when gates allow; mass wave requires explicit approval):

```bash
ALLOW_SCHEDULED_LIFECYCLE_PUBLICATION=true bash scripts/server_publication_lifecycle_scheduled.sh
```

First wave when most catalog is &gt;7 days old:

```bash
ALLOW_SCHEDULED_LIFECYCLE_PUBLICATION=true ALLOW_MASS_LIFECYCLE_DEPRECATION=true \
  ALLOW_PILOT_TO_PRODUCTION_PROMOTION=true bash scripts/server_publication_lifecycle_scheduled.sh
```

**Never** run `promote_pilot sync-apply --deprecate` manually without `lifecycle-preview`, backup, and locks.

## Rollback (code)

```bash
cd /var/www/linkedin-job-scrapper
git fetch origin
git checkout <previous_sha>
$COMPOSE build api api-pilot worker-linkedin
$COMPOSE up -d api api-pilot
```

Restore Mongo from `evidence/promotion_backups/` promotion backups if lifecycle apply was wrong.

## Job alerts

`app/modules/alerts/` is **foundation only** — no subscriber persistence API, no push credentials, no device delivery. Not production-ready for notifications.
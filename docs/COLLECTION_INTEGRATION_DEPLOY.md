# Production deploy — LinkedIn scraper (no live collection until auth restored)

## Throughput (corrected)

**30 live runs/day × 15 jobs/run = ≤450 fetched records/day** (before dedup/filters). **300–500 unique new jobs/day is not guaranteed.**

## Compose (required file order)

Containers when project `linkedin-scraper` is up on Contabo:

| Service       | Container name                  |
|---------------|---------------------------------|
| Production API| `linkedin-scraper-api`          |
| Pilot API     | `linkedin-scraper-api-pilot`    |
| MongoDB       | `linkedin-scraper-mongodb`      |
| Redis         | `linkedin-scraper-redis`        |
| LinkedIn worker | `linkedin-scraper-worker-linkedin` |
| Beat          | `linkedin-scraper-beat`         |

```bash
cd /var/www/linkedin-job-scrapper
source scripts/lib_compose.sh
"${COMPOSE[@]}" config --services   # verify api, api-pilot, mongodb, redis, worker-linkedin, beat
```

## Cron timezone

Crontab installed by `server_install_production_ops_cron.sh` sets **`CRON_TZ=UTC`**. VPS local offset may differ — confirm:

```bash
timedatectl
crontab -l | head -1
```

| UTC (cron)   | Job                                      |
|--------------|------------------------------------------|
| `*/10 * * * *` | Observer watchdog                     |
| `30 */6 * * *` | Publication upsert sync (no deprecate) |
| `0 */6 * * *`  | Read-only monitor                     |
| `15 3 * * *`   | Job expiry (pilot apply only by default) |
| `45 3 * * 0`   | Lifecycle publication (gated)            |

## Copy-paste deploy procedure (code + APIs only — **do not** activate Wave 1)

```bash
cd /var/www/linkedin-job-scrapper
source scripts/lib_compose.sh
export DEPLOY_SHA=REPLACE_WITH_VERIFIED_SHA

git fetch origin
git checkout "$DEPLOY_SHA"
git rev-parse HEAD

"${COMPOSE[@]}" build api api-pilot
"${COMPOSE[@]}" up -d mongodb redis
"${COMPOSE[@]}" up -d api api-pilot
docker ps --format 'table {{.Names}}\t{{.Status}}' | grep linkedin-scraper

# Preview seven-day impact (read-only, both DBs)
ALLOW_SCHEDULED_JOB_EXPIRY=true \
  JOB_EXPIRY_APPLY_PILOT=false JOB_EXPIRY_PRODUCTION_APPLY=false \
  bash scripts/server_job_expiry_scheduled.sh
ls -1t evidence/job_lifecycle/expiry_preview_*.json | head -1 | xargs cat

docker exec linkedin-scraper-api-pilot python -m app.cli.promote_pilot lifecycle-preview
```

### First production expiry wave (operator approval only)

```bash
bash scripts/server_mongo_backup_jobs.sh global_jobs_pilot
bash scripts/server_mongo_backup_jobs.sh global_jobs

ALLOW_SCHEDULED_JOB_EXPIRY=true \
  JOB_EXPIRY_APPLY_PILOT=true JOB_EXPIRY_PRODUCTION_APPLY=true \
  bash scripts/server_job_expiry_scheduled.sh

# Optional: propagate expired pilot rows to production (mass gate may block — see lifecycle-preview)
ALLOW_SCHEDULED_LIFECYCLE_PUBLICATION=true \
  ALLOW_PILOT_TO_PRODUCTION_PROMOTION=true \
  ALLOW_MASS_LIFECYCLE_DEPRECATION=true \
  bash scripts/server_publication_lifecycle_scheduled.sh
```

### Post-deploy API checks

```bash
curl -fsS https://jobsfinder.batteryanimation2.com/api/v1/jobs/stats | python3 -m json.tool
curl -fsS "https://jobsfinder.batteryanimation2.com/api/v1/jobs?page=1&page_size=5" | python3 -m json.tool
curl -fsS https://jobsfinder.batteryanimation2.com/api/v1/jobs/countries | python3 -m json.tool
```

After expiry, expect **`total_active`** and list **`total`** to drop for jobs older than seven days; sorting remains **newest `posted_at` / `first_seen_at` first**.

## 10/15 job trials (when auth restored — separate step)

On worker only after explicit approval, set in `compose.contabo-wave1.yaml` (or env):

- `LINKEDIN_HONOR_TARGET_BATCH_SIZES=true`
- Keep `LINKEDIN_MAX_LIVE_JOBS_PER_RUN=5` unless intentionally raising the default soft cap

```bash
export WAVE1_ENABLE_GROUP=software_expanded_10
export WAVE1_MAX_JOBS_PER_RUN=10
# bash scripts/server_wave1_activate.sh   # ONLY after session refresh + operator sign-off
```

Default without honor flag: targets configured for 10/15 still dispatch **max 5** jobs/run.

## Rollback

```bash
cd /var/www/linkedin-job-scrapper
source scripts/lib_compose.sh
git checkout 2d0b1f4
"${COMPOSE[@]}" build api api-pilot
"${COMPOSE[@]}" up -d api api-pilot
# Restore Mongo from evidence/mongo_backups/*/ if expiry was applied in error
```

**Do not** use `docker compose down -v` or volume prune.

## Job alerts

`app/modules/alerts/` — **incomplete** (no subscriber DB, no push delivery).
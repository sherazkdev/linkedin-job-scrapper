#!/usr/bin/env bash
# Sanitized VPS pilot/redis/mongo snapshot (no secrets printed).
set -euo pipefail

APP_DIR=/var/www/linkedin-job-scrapper
cd "$APP_DIR"
PILOT_DB=global_jobs_pilot
COMPOSE="docker compose -f compose.yaml -f compose.contabo-vps.yaml -p linkedin-scraper"

log() { echo "[$(date -u +%Y-%m-%dT%H:%M:%SZ)] $*" >&2; }

log "STEP docker_linkedin"
docker ps -a --filter name=linkedin --format 'table {{.Names}}\t{{.Status}}\t{{.State}}' | head -25

log "STEP mongo_pilot_state"
MONGO_USER=$(timeout 30 docker exec linkedin-scraper-mongodb printenv MONGO_INITDB_ROOT_USERNAME)
MONGO_PASS=$(timeout 30 docker exec linkedin-scraper-mongodb printenv MONGO_INITDB_ROOT_PASSWORD)
timeout 45 docker exec linkedin-scraper-mongodb mongosh -u "$MONGO_USER" -p "$MONGO_PASS" \
  --authenticationDatabase admin --quiet --eval "
const dbp = db.getSiblingDB('${PILOT_DB}');
const running = dbp.collection_runs.countDocuments({ source: 'linkedin', status: 'running' });
const enabled = dbp.collection_targets.countDocuments({ source: 'linkedin', enabled: true });
const locked = dbp.collection_targets.countDocuments({
  source: 'linkedin',
  lock_owner: { \$ne: null },
  locked_until: { \$gte: new Date() },
});
const target = dbp.collection_targets.findOne(
  { source: 'linkedin', country_code: 'PK', keyword: 'junior erp consultant' },
  { search_location: 1, enabled: 1, lock_owner: 1, locked_until: 1, next_eligible_at: 1 }
);
const lastRun = dbp.collection_runs.find({ source: 'linkedin' }).sort({ started_at: -1 }).limit(1).toArray()[0];
printjson({
  running_runs: running,
  enabled_targets: enabled,
  active_locks: locked,
  jobs: dbp.jobs.countDocuments({ source: 'linkedin' }),
  target,
  latest_run: lastRun && {
    run_id: lastRun.run_id,
    status: lastRun.status,
    search_location: lastRun.search_location,
    error_summary: lastRun.error_summary,
    started_at: lastRun.started_at,
  },
});
"

log "STEP redis_collection_queue"
REDIS_PASS=$(timeout 30 docker exec linkedin-scraper-redis printenv REDIS_PASSWORD)
QUEUE=$($COMPOSE exec -T redis printenv CELERY_TASK_DEFAULT_QUEUE 2>/dev/null || echo "collection")
DEPTH=$(timeout 15 docker exec linkedin-scraper-redis redis-cli -a "$REDIS_PASS" --no-auth-warning LLEN "$QUEUE" 2>/dev/null || echo "unavailable")
echo "queue_name=$QUEUE queue_depth=$DEPTH"

log "STEP celery_scheduled"
timeout 30 docker exec linkedin-scraper-worker-linkedin celery -A app.workers.celery_app inspect scheduled 2>/dev/null \
  | head -5 || echo "steady_worker_unavailable"

log "STEP https"
timeout 15 curl -sf https://jobsfinder.batteryanimation2.com/health/live && echo " HTTPS_OK"

log "STEP inspect_done"
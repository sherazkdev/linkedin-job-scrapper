#!/usr/bin/env bash
# Safe cleanup after a stuck or aborted pilot — no live dispatch, no volume destruction.
set -euo pipefail

APP_DIR=/var/www/linkedin-job-scrapper
cd "$APP_DIR"
COMPOSE="docker compose -f compose.yaml -f compose.contabo-vps.yaml -p linkedin-scraper"
PILOT_DB=global_jobs_pilot
MONGO_USER=$(docker exec linkedin-scraper-mongodb printenv MONGO_INITDB_ROOT_USERNAME)
MONGO_PASS=$(docker exec linkedin-scraper-mongodb printenv MONGO_INITDB_ROOT_PASSWORD)

log() { echo "[$(date -u +%Y-%m-%dT%H:%M:%SZ)] $*" >&2; }

log "STEP reconcile_start"

if docker ps -a --format '{{.Names}}' | grep -qx linkedin-pilot-live-once; then
  log "STEP stop_pilot_container"
  timeout --foreground 120 docker stop -t 15 linkedin-pilot-live-once || \
    timeout --foreground 30 docker kill linkedin-pilot-live-once || true
  docker rm -f linkedin-pilot-live-once 2>/dev/null || true
else
  log "STEP pilot_container_absent"
fi

if ! docker ps --format '{{.Names}}' | grep -qx linkedin-scraper-worker-linkedin; then
  log "STEP restore_steady_worker"
  timeout --foreground 180 $COMPOSE --profile celery-linkedin up -d worker-linkedin
fi

log "STEP mongo_disable_targets_clear_locks"
timeout --foreground 60 docker exec linkedin-scraper-mongodb mongosh -u "$MONGO_USER" -p "$MONGO_PASS" \
  --authenticationDatabase admin --quiet --eval "
const dbp = db.getSiblingDB('${PILOT_DB}');
dbp.collection_targets.updateMany(
  { source: 'linkedin' },
  { \$set: { enabled: false, lock_owner: null, locked_until: null } }
);
const n = dbp.collection_runs.updateMany(
  { source: 'linkedin', status: 'running' },
  { \$set: { status: 'cancelled', error_summary: 'pilot_reconcile_manual', finished_at: new Date() } }
);
printjson({ disabled_targets: true, cancelled_running: n.modifiedCount });
"

log "STEP health_checks"
docker ps --filter name=linkedin-scraper --format 'table {{.Names}}\t{{.Status}}' | head -20
curl -sf https://jobsfinder.batteryanimation2.com/health/live && echo " HTTPS_OK" || echo " HTTPS_FAIL"

log "STEP reconcile_done"
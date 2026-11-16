#!/usr/bin/env bash
set -euo pipefail
APP_DIR=/var/www/linkedin-job-scrapper
cd "$APP_DIR"
PILOT_DB=global_jobs_pilot
log() { echo "[$(date -u +%Y-%m-%dT%H:%M:%SZ)] $*" >&2; }

log "STEP sha=$(git rev-parse --short HEAD)"
docker ps --filter name=linkedin-scraper-beat --format '{{.Names}}' | grep -q . && exit 2 || log "STEP beat_absent"
REDIS_PASS=$(docker exec linkedin-scraper-redis printenv REDIS_PASSWORD)
DEPTH=$(docker exec linkedin-scraper-redis redis-cli -a "$REDIS_PASS" --no-auth-warning LLEN collection)
log "STEP redis_queue_depth=$DEPTH"
SCHED=$(docker exec linkedin-scraper-worker-linkedin celery -A app.workers.celery_app inspect scheduled 2>/dev/null | wc -c)
log "STEP celery_scheduled_bytes=$SCHED"
MONGO_USER=$(docker exec linkedin-scraper-mongodb printenv MONGO_INITDB_ROOT_USERNAME)
MONGO_PASS=$(docker exec linkedin-scraper-mongodb printenv MONGO_INITDB_ROOT_PASSWORD)
docker exec linkedin-scraper-mongodb mongosh -u "$MONGO_USER" -p "$MONGO_PASS" --authenticationDatabase admin --quiet --eval "
const dbp=db.getSiblingDB('${PILOT_DB}');
printjson({
  enabled_targets: dbp.collection_targets.countDocuments({source:'linkedin',enabled:true}),
  running_runs: dbp.collection_runs.countDocuments({source:'linkedin',status:'running'}),
});
"
docker exec linkedin-scraper-worker-linkedin python -m app.cli.linkedin_session status
curl -sf https://jobsfinder.batteryanimation2.com/health/live && echo " HTTPS_OK"
log "STEP preflight_ok"
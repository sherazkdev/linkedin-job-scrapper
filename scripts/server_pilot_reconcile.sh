#!/usr/bin/env bash
# Safe cleanup after a stuck or aborted pilot — no live dispatch, no volume destruction.
set -euo pipefail

APP_DIR=/var/www/linkedin-job-scrapper
cd "$APP_DIR"
COMPOSE="docker compose -f compose.yaml -f compose.contabo-vps.yaml -p linkedin-scraper"
PILOT_DB=global_jobs_pilot
PILOT_CONTAINER=linkedin-pilot-live-once
D_MONGO=60
D_DOCKER=120
D_COMPOSE=180
D_CELERY=45

MONGO_USER=$(timeout 30 docker exec linkedin-scraper-mongodb printenv MONGO_INITDB_ROOT_USERNAME)
MONGO_PASS=$(timeout 30 docker exec linkedin-scraper-mongodb printenv MONGO_INITDB_ROOT_PASSWORD)

log() { echo "[$(date -u +%Y-%m-%dT%H:%M:%SZ)] $*" >&2; }

mongo_eval() {
  timeout "$D_MONGO" docker exec linkedin-scraper-mongodb mongosh -u "$MONGO_USER" -p "$MONGO_PASS" \
    --authenticationDatabase admin --quiet --eval "$1"
}

celery_on_pilot() {
  if docker ps --format '{{.Names}}' | grep -qx "$PILOT_CONTAINER"; then
    timeout "$D_CELERY" docker exec "$PILOT_CONTAINER" celery -A app.workers.celery_app "$@"
  fi
}

log "STEP reconcile_start"

log "STEP mongo_disable_targets_clear_locks"
mongo_eval "
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

if docker ps --format '{{.Names}}' | grep -qx "$PILOT_CONTAINER"; then
  log "STEP revoke_pilot_active_and_scheduled"
  ACTIVE_JSON=$(celery_on_pilot inspect active 2>/dev/null || echo "{}")
  SCHED_JSON=$(celery_on_pilot inspect scheduled 2>/dev/null || echo "{}")
  mapfile -t TASK_IDS < <(printf '%s\n%s' "$ACTIVE_JSON" "$SCHED_JSON" | python3 -c "
import json,sys
ids=set()
for line in sys.stdin:
  line=line.strip()
  if not line: continue
  try:
    data=json.loads(line)
  except json.JSONDecodeError:
    continue
  if not isinstance(data,dict): continue
  for _w, tasks in data.items():
    if not isinstance(tasks,list): continue
    for t in tasks:
      if isinstance(t,dict):
        tid=t.get('id') or (t.get('request') or {}).get('id')
        if tid: ids.add(tid)
print('\n'.join(sorted(ids)))
" 2>/dev/null || true)
  for tid in "${TASK_IDS[@]:-}"; do
    [ -z "$tid" ] && continue
    log "STEP revoke task_id=$tid"
    celery_on_pilot control revoke --terminate "$tid" 2>/dev/null || true
  done
fi

if docker ps -a --format '{{.Names}}' | grep -qx "$PILOT_CONTAINER"; then
  log "STEP stop_pilot_container"
  timeout "$D_DOCKER" docker stop -t 15 "$PILOT_CONTAINER" 2>/dev/null || \
    timeout 30 docker kill "$PILOT_CONTAINER" 2>/dev/null || true
  docker rm -f "$PILOT_CONTAINER" 2>/dev/null || true
else
  log "STEP pilot_container_absent"
fi

log "STEP restore_steady_worker_live_off"
timeout "$D_COMPOSE" $COMPOSE --profile celery-linkedin up -d worker-linkedin

log "STEP verify_beat_absent"
if docker ps --format '{{.Names}}' | grep -q linkedin-scraper-beat; then
  log "WARN beat_container_present"
else
  log "STEP beat_absent_ok"
fi

log "STEP health_checks"
docker ps --filter name=linkedin-scraper --format 'table {{.Names}}\t{{.Status}}' | head -20
timeout 20 curl -sf https://jobsfinder.batteryanimation2.com/health/live && echo " HTTPS_OK" || echo " HTTPS_FAIL"

log "STEP reconcile_done"
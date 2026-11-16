#!/usr/bin/env bash
set -euo pipefail
APP_DIR=/var/www/linkedin-job-scrapper
cd "$APP_DIR"
COMPOSE="docker compose -f compose.yaml -f compose.contabo-vps.yaml -f compose.contabo-pilot.yaml -p linkedin-scraper"
PILOT_DB=global_jobs_pilot

# Bounded timeouts (seconds) — prevents silent hangs on docker/mongosh/curl.
D_MONGO=45
D_COMPOSE=180
D_DOCKER=120
D_DISPATCH=120
D_CELERY_PING=60
D_WAIT_POLLS=120          # 120 * POLL_SLEEP = max wait phase
POLL_SLEEP=5
NO_NEW_RUN_ABORT_POLLS=24 # ~2 min without a post-dispatch run -> exit wait
RUNNING_STALL_POLLS=180    # ~15 min in 'running' -> cancel in DB and exit wait
D_STOP_PILOT=120
D_HEALTH=30

MONGO_USER=$(timeout "$D_MONGO" docker exec linkedin-scraper-mongodb printenv MONGO_INITDB_ROOT_USERNAME)
MONGO_PASS=$(timeout "$D_MONGO" docker exec linkedin-scraper-mongodb printenv MONGO_INITDB_ROOT_PASSWORD)

log() { echo "[$(date -u +%Y-%m-%dT%H:%M:%SZ)] $*" >&2; }

mongo_eval() {
  timeout "$D_MONGO" docker exec linkedin-scraper-mongodb mongosh -u "$MONGO_USER" -p "$MONGO_PASS" \
    --authenticationDatabase admin --quiet --eval "$1"
}

log "STEP migrate_pilot_index"
mongo_eval "
const dbp = db.getSiblingDB('${PILOT_DB}');
const t = dbp.collection_targets;
const idx = t.getIndexes().find(i => i.name === 'uniq_target_source_country_keyword');
if (idx && !idx.key.search_location) {
  t.dropIndex('uniq_target_source_country_keyword');
  t.updateMany({ search_location: { \$exists: false } }, { \$set: { search_location: '' } });
  t.createIndex({ source: 1, country_code: 1, keyword: 1, search_location: 1 }, { unique: true, name: 'uniq_target_source_country_keyword' });
}
printjson({ indexes: t.getIndexes().map(i => i.name) });
"

log "STEP clear_stale_runs"
mongo_eval "
const dbp = db.getSiblingDB('${PILOT_DB}');
const n = dbp.collection_runs.updateMany(
  { source: 'linkedin', status: 'running' },
  { \$set: { status: 'cancelled', error_summary: 'pilot_pre_dispatch_reset', finished_at: new Date() } }
);
printjson({ cancelled_running: n.modifiedCount });
"

log "STEP enable_target"
mongo_eval "
const dbp = db.getSiblingDB('${PILOT_DB}');
dbp.collection_targets.updateMany({ source: 'linkedin' }, { \$set: { enabled: false, lock_owner: null, locked_until: null } });
dbp.collection_targets.updateOne(
  { source: 'linkedin', country_code: 'PK', keyword: 'junior erp consultant', search_location: 'islamabad, pakistan' },
  { \$set: { enabled: true, max_jobs_per_run: 1, lock_owner: null, locked_until: null, priority: 200 } },
  { upsert: true }
);
printjson({ enabled: dbp.collection_targets.countDocuments({ source: 'linkedin', enabled: true }) });
"

log "STEP stop_steady_worker"
timeout "$D_DOCKER" docker stop linkedin-scraper-worker-linkedin || true

log "STEP remove_old_pilot_container"
timeout "$D_DOCKER" docker rm -f linkedin-pilot-live-once 2>/dev/null || true

log "STEP start_pilot_worker"
timeout "$D_COMPOSE" $COMPOSE --profile celery-linkedin run -d --name linkedin-pilot-live-once \
  -e ALLOW_LIVE_LINKEDIN_COLLECTION=true \
  -e CELERY_ALLOW_LINKEDIN_TASKS=true \
  -e CELERY_WORKER_MONGO_DB_NAME="$PILOT_DB" \
  -e CELERY_DISPATCH_SOURCE_ALLOWLIST=linkedin \
  -e ALLOW_COLLECTION_TARGET_INDEX_MIGRATION=true \
  worker-linkedin

log "STEP wait_pilot_worker_ping"
for i in $(seq 1 24); do
  if timeout "$D_CELERY_PING" docker exec linkedin-pilot-live-once celery -A app.workers.celery_app inspect ping 2>/dev/null | grep -q pong; then
    log "STEP pilot_ping ok poll=$i"
    break
  fi
  if [ "$i" -eq 24 ]; then
    log "ERROR pilot_ping_timeout"
    exit 11
  fi
  sleep 5
done

MARK=$(date -u +%Y-%m-%dT%H:%M:%SZ)
log "STEP dispatch_once mark=$MARK"

TASK_ID="collect-linkedin-PK-junior_erp_consultant-islamabad_pakistan"
log "STEP revoke_prior_task_id=$TASK_ID"
timeout "$D_CELERY_PING" docker exec linkedin-pilot-live-once celery -A app.workers.celery_app control revoke \
  --terminate "$TASK_ID" 2>/dev/null || true

DISPATCH_OUT=$(timeout "$D_DISPATCH" docker exec -w /app \
  -e CELERY_WORKER_MONGO_DB_NAME="$PILOT_DB" \
  -e CELERY_DISPATCH_SOURCE_ALLOWLIST=linkedin \
  linkedin-pilot-live-once python -m app.cli.celery_ops dispatch-once)
echo "$DISPATCH_OUT"

NEW_RUN_SEEN=0
RUNNING_POLLS=0
log "STEP wait_collection max_polls=$D_WAIT_POLLS poll_sleep=${POLL_SLEEP}s"

for i in $(seq 1 "$D_WAIT_POLLS"); do
  RUN_LINE=$(mongo_eval "
const r=db.getSiblingDB('${PILOT_DB}').collection_runs.find({source:'linkedin'}).sort({started_at:-1}).limit(1).toArray()[0];
if (!r) { print('none|none|none'); } else { print([r.status,r.run_id,r.started_at && r.started_at.toISOString()].join('|')); }
")
  RUNS=$(echo "$RUN_LINE" | cut -d'|' -f1)
  RUN_ID=$(echo "$RUN_LINE" | cut -d'|' -f2)
  RUN_START=$(echo "$RUN_LINE" | cut -d'|' -f3)
  JOBS=$(mongo_eval "print(db.getSiblingDB('${PILOT_DB}').jobs.countDocuments({source:'linkedin'}))")
  log "WAIT poll=$i status=$RUNS run_id=$RUN_ID run_start=$RUN_START jobs=$JOBS mark=$MARK"

  if [ "$RUN_START" != "none" ] && [[ "$RUN_START" > "$MARK" ]]; then
    NEW_RUN_SEEN=1
    if [ "$RUNS" = "completed" ] || [ "$RUNS" = "failed" ] || [ "$RUNS" = "cancelled" ]; then
      log "STEP wait_done terminal_status=$RUNS"
      break
    fi
    if [ "$RUNS" = "running" ]; then
      RUNNING_POLLS=$((RUNNING_POLLS + 1))
      if [ "$RUNNING_POLLS" -ge "$RUNNING_STALL_POLLS" ]; then
        log "ERROR running_stall cancelling run_id=$RUN_ID"
        mongo_eval "db.getSiblingDB('${PILOT_DB}').collection_runs.updateOne({run_id:'${RUN_ID}'},{ \$set:{status:'cancelled',error_summary:'pilot_wait_stall',finished_at:new Date()}})"
        break
      fi
    fi
  fi

  if [ "$NEW_RUN_SEEN" -eq 0 ] && [ "$i" -ge "$NO_NEW_RUN_ABORT_POLLS" ]; then
    log "ERROR no_new_run_after_dispatch polls=$i"
    break
  fi

  sleep "$POLL_SLEEP"
done

log "STEP results_summary"
mongo_eval "
const dbp = db.getSiblingDB('${PILOT_DB}');
const jobs = dbp.jobs.find({ source: 'linkedin' }).sort({ last_seen_at: -1 }).limit(2).toArray();
printjson({ count: dbp.jobs.countDocuments({ source: 'linkedin' }), sample: jobs.map(j => ({ id: j.sourceJobId, title: j.title, prov: j.data_provenance })) });
const run = dbp.collection_runs.find({ source: 'linkedin' }).sort({ started_at: -1 }).limit(1).toArray();
printjson({ latest_run: run[0] && { run_id: run[0].run_id, status: run[0].status, err: run[0].error_summary, stats: run[0].stats } });
"

timeout 15 docker stats --no-stream linkedin-pilot-live-once 2>/dev/null || true
docker logs --tail 40 linkedin-pilot-live-once 2>&1 | grep -Ei 'phase=|chromium|search_|live_fetch|ERROR|Collection task|unsupported' | tail -20 || true

log "STEP pilot_cleanup"
mongo_eval "db.getSiblingDB('${PILOT_DB}').collection_targets.updateMany({source:'linkedin'},{ \$set:{enabled:false}})"
timeout "$D_STOP_PILOT" docker stop -t 15 linkedin-pilot-live-once && timeout 30 docker rm linkedin-pilot-live-once

log "STEP restore_steady_worker"
timeout "$D_COMPOSE" $COMPOSE --profile celery-linkedin up -d worker-linkedin

log "STEP https_health"
timeout "$D_HEALTH" curl -sf https://jobsfinder.batteryanimation2.com/health/live && echo "HTTPS_OK"

log "STEP pilot_script_done"
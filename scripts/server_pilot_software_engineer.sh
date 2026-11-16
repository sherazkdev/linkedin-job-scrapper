#!/usr/bin/env bash
# ONE live pilot: PK / Islamabad / Software Engineer / max_jobs=10 / global_jobs_pilot
set -euo pipefail
APP_DIR=/var/www/linkedin-job-scrapper
cd "$APP_DIR"
COMPOSE="docker compose -f compose.yaml -f compose.contabo-vps.yaml -f compose.contabo-pilot.yaml -p linkedin-scraper"
PILOT_DB=global_jobs_pilot
PILOT_CONTAINER=linkedin-pilot-live-once
PILOT_KEYWORD="software engineer"
PILOT_MAX_JOBS=10
PILOT_LOCATION="islamabad, pakistan"

D_MONGO=45
D_COMPOSE=180
D_DOCKER=120
D_DISPATCH=120
D_WAIT_POLLS=180
POLL_SLEEP=5
NO_NEW_RUN_ABORT_POLLS=36
RUNNING_STALL_POLLS=150
D_STOP_PILOT=120
D_HEALTH=30

MONGO_USER=$(timeout "$D_MONGO" docker exec linkedin-scraper-mongodb printenv MONGO_INITDB_ROOT_USERNAME)
MONGO_PASS=$(timeout "$D_MONGO" docker exec linkedin-scraper-mongodb printenv MONGO_INITDB_ROOT_PASSWORD)

log() { echo "[$(date -u +%Y-%m-%dT%H:%M:%SZ)] $*" >&2; }

mongo_eval() {
  timeout "$D_MONGO" docker exec linkedin-scraper-mongodb mongosh -u "$MONGO_USER" -p "$MONGO_PASS" \
    --authenticationDatabase admin --quiet --eval "$1"
}

pilot_cleanup() {
  log "CLEANUP disable_pilot_targets"
  mongo_eval "db.getSiblingDB('${PILOT_DB}').collection_targets.updateMany(
    { source: 'linkedin' },
    { \$set: { enabled: false, lock_owner: null, locked_until: null } }
  )" 2>/dev/null || true
  if docker ps -a --format '{{.Names}}' | grep -qx "$PILOT_CONTAINER"; then
    timeout "$D_STOP_PILOT" docker stop -t 15 "$PILOT_CONTAINER" 2>/dev/null || \
      timeout 30 docker kill "$PILOT_CONTAINER" 2>/dev/null || true
    timeout 30 docker rm -f "$PILOT_CONTAINER" 2>/dev/null || true
  fi
  docker rm -f linkedin-pilot-api-verify 2>/dev/null || true
  timeout "$D_COMPOSE" $COMPOSE --profile celery-linkedin up -d worker-linkedin 2>/dev/null || true
}

trap 'pilot_cleanup' EXIT INT TERM

log "STEP preflight_disable_targets"
mongo_eval "
const dbp = db.getSiblingDB('${PILOT_DB}');
dbp.collection_targets.updateMany({ source: 'linkedin' }, { \$set: { enabled: false, lock_owner: null, locked_until: null } });
dbp.collection_runs.updateMany({ source: 'linkedin', status: 'running' }, { \$set: { status: 'cancelled', error_summary: 'pilot_pre_reset', finished_at: new Date() } });
"

log "STEP enable_software_engineer_target max_jobs=${PILOT_MAX_JOBS}"
mongo_eval "
const dbp = db.getSiblingDB('${PILOT_DB}');
dbp.collection_targets.updateOne(
  { source: 'linkedin', country_code: 'PK', keyword: '${PILOT_KEYWORD}', search_location: '${PILOT_LOCATION}' },
  { \$set: { enabled: true, max_jobs_per_run: ${PILOT_MAX_JOBS}, lock_owner: null, locked_until: null, priority: 200, country_name: 'Pakistan' } },
  { upsert: true }
);
printjson({ enabled: dbp.collection_targets.countDocuments({ source: 'linkedin', enabled: true }) });
"

timeout "$D_DOCKER" docker stop linkedin-scraper-worker-linkedin 2>/dev/null || true
timeout "$D_DOCKER" docker rm -f "$PILOT_CONTAINER" 2>/dev/null || true

log "STEP start_pilot_worker"
timeout "$D_COMPOSE" $COMPOSE --profile celery-linkedin run -d --name "$PILOT_CONTAINER" \
  -e ALLOW_LIVE_LINKEDIN_COLLECTION=true \
  -e CELERY_ALLOW_LINKEDIN_TASKS=true \
  -e CELERY_WORKER_MONGO_DB_NAME="$PILOT_DB" \
  -e CELERY_DISPATCH_SOURCE_ALLOWLIST=linkedin \
  worker-linkedin

ready_ok=0
for i in $(seq 1 60); do
  if docker logs "$PILOT_CONTAINER" 2>&1 | grep -qE "linkedin-worker@[^ ]+ ready\.'"; then
    ready_ok=1
    log "STEP pilot_ready poll=$i"
    break
  fi
  sleep 3
done
[ "$ready_ok" -eq 1 ] || { log "ERROR pilot_not_ready"; exit 11; }

MARK=$(date -u +%Y-%m-%dT%H:%M:%SZ)
DISPATCH_OUT=$(timeout "$D_DISPATCH" docker exec -w /app \
  -e CELERY_WORKER_MONGO_DB_NAME="$PILOT_DB" \
  -e CELERY_ALLOW_LINKEDIN_TASKS=true \
  -e ALLOW_LIVE_LINKEDIN_COLLECTION=true \
  "$PILOT_CONTAINER" python -m app.cli.celery_ops pilot-dispatch-once \
  --source linkedin --country-code PK --keyword "$PILOT_KEYWORD" \
  --search-location "$PILOT_LOCATION" --max-jobs "$PILOT_MAX_JOBS")
echo "$DISPATCH_OUT"
PILOT_TASK_ID=$(echo "$DISPATCH_OUT" | python3 -c "import sys,json; print(json.load(sys.stdin).get('task_id',''))" 2>/dev/null || echo "")

NEW_RUN_SEEN=0
RUNNING_POLLS=0
RUNS=none
for i in $(seq 1 "$D_WAIT_POLLS"); do
  RUN_LINE=$(mongo_eval "
const r=db.getSiblingDB('${PILOT_DB}').collection_runs.find({source:'linkedin'}).sort({started_at:-1}).limit(1).toArray()[0];
if (!r) { print('none|none|none'); } else { print([r.status,r.run_id,r.started_at && r.started_at.toISOString()].join('|')); }
")
  RUNS=$(echo "$RUN_LINE" | cut -d'|' -f1)
  RUN_ID=$(echo "$RUN_LINE" | cut -d'|' -f2)
  RUN_START=$(echo "$RUN_LINE" | cut -d'|' -f3)
  JOBS=$(mongo_eval "print(db.getSiblingDB('${PILOT_DB}').jobs.countDocuments({source:'linkedin'}))")
  log "WAIT poll=$i status=$RUNS jobs=$JOBS mark=$MARK"
  if [ "$RUN_START" != "none" ] && [[ "$RUN_START" > "$MARK" ]]; then
    NEW_RUN_SEEN=1
    if [ "$RUNS" = "completed" ] || [ "$RUNS" = "failed" ] || [ "$RUNS" = "cancelled" ]; then
      break
    fi
  fi
  if [ "$RUNS" = "running" ] && [ "$NEW_RUN_SEEN" -eq 1 ]; then
    RUNNING_POLLS=$((RUNNING_POLLS + 1))
    [ "$RUNNING_POLLS" -lt "$RUNNING_STALL_POLLS" ] || {
      [ -n "$PILOT_TASK_ID" ] && docker exec "$PILOT_CONTAINER" celery -A app.workers.celery_app control revoke --terminate "$PILOT_TASK_ID" 2>/dev/null || true
      mongo_eval "db.getSiblingDB('${PILOT_DB}').collection_runs.updateOne({run_id:'$RUN_ID'},{ \$set:{status:'cancelled',error_summary:'pilot_stall',finished_at:new Date()}})"
      break
    }
  fi
  [ "$NEW_RUN_SEEN" -eq 0 ] && [ "$i" -ge "$NO_NEW_RUN_ABORT_POLLS" ] && break
  sleep "$POLL_SLEEP"
done

log "STEP mongo_summary"
mongo_eval "
const dbp = db.getSiblingDB('${PILOT_DB}');
const jobs = dbp.jobs.find({ source: 'linkedin' }).sort({ last_seen_at: -1 }).limit(5).toArray();
printjson({
  jobs_count: dbp.jobs.countDocuments({ source: 'linkedin' }),
  jobs: jobs.map(j => ({
    sourceJobId: j.sourceJobId,
    title: j.title,
    company: j.company,
    location: j.location_text,
    posted_at: j.posted_at,
    data_provenance: j.data_provenance,
    job_url: j.job_url,
  })),
  latest_run: dbp.collection_runs.find({ source: 'linkedin' }).sort({ started_at: -1 }).limit(1).toArray().map(r => ({
    run_id: r.run_id, status: r.status, stats: r.stats, error_summary: r.error_summary
  }))[0],
});
"

docker logs --tail 120 "$PILOT_CONTAINER" 2>&1 | grep -Ei 'rejected_|jobs_collected|search_dom_snapshot|cards_count|created_count|detail skip|adapter_rejected|normalized|mongo_persist|Worker collection finished' | tail -35 || true

log "STEP pilot_api_verify"
docker rm -f linkedin-pilot-api-verify 2>/dev/null || true
timeout "$D_COMPOSE" $COMPOSE run -d --name linkedin-pilot-api-verify \
  -p 127.0.0.1:18097:8000 \
  -e MONGO_DB_NAME="$PILOT_DB" \
  api
for i in $(seq 1 30); do
  if curl -sf http://127.0.0.1:18097/health/live >/dev/null; then break; fi
  sleep 2
done
curl -sf "http://127.0.0.1:18097/api/v1/jobs?source=linkedin&country_code=PK&page_size=5" | python3 -m json.tool | head -80 || echo "API_FETCH_FAILED"
curl -sf http://127.0.0.1:18095/health/live >/dev/null && echo "PRODUCTION_API_OK"

trap - EXIT INT TERM
pilot_cleanup
log "STEP done"
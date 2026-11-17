#!/usr/bin/env bash
# Controlled multi-country pilot (5 countries, 1 job each max) — requires LIVE_MULTI_COUNTRY_APPROVE=1
set -euo pipefail
if [ "${LIVE_MULTI_COUNTRY_APPROVE:-}" != "1" ]; then
  echo "Refusing live batch: set LIVE_MULTI_COUNTRY_APPROVE=1 after explicit approval" >&2
  exit 2
fi

APP_DIR=/var/www/linkedin-job-scrapper
cd "$APP_DIR"
COMPOSE="docker compose -f compose.yaml -f compose.contabo-vps.yaml -f compose.contabo-pilot.yaml -p linkedin-scraper"
PILOT_DB=global_jobs_pilot
PILOT_CONTAINER=linkedin-pilot-multi-country
KEYWORD="software engineer"
MAX_JOBS_PER_COUNTRY=1

COUNTRIES=(PK GB US DE AE)
COUNTRY_NAMES=("Pakistan" "United Kingdom" "United States" "Germany" "United Arab Emirates")

D_MONGO=45
D_COMPOSE=180
D_DISPATCH=60
POLL_SLEEP=5
COUNTRY_POLL_MAX=120
COUNTRY_WALL_SEC=600
STALL_RUNNING_POLLS=90

MONGO_USER=$(timeout "$D_MONGO" docker exec linkedin-scraper-mongodb printenv MONGO_INITDB_ROOT_USERNAME)
MONGO_PASS=$(timeout "$D_MONGO" docker exec linkedin-scraper-mongodb printenv MONGO_INITDB_ROOT_PASSWORD)

log() { echo "[$(date -u +%Y-%m-%dT%H:%M:%SZ)] $*" >&2; }

mongo_eval() {
  timeout "$D_MONGO" docker exec linkedin-scraper-mongodb mongosh -u "$MONGO_USER" -p "$MONGO_PASS" \
    --authenticationDatabase admin --quiet --eval "$1"
}

pilot_cleanup() {
  log "CLEANUP disable_pilot_targets restore_steady_worker"
  mongo_eval "db.getSiblingDB('${PILOT_DB}').collection_targets.updateMany(
    { source: 'linkedin' }, { \$set: { enabled: false, lock_owner: null, locked_until: null } }
  )" 2>/dev/null || true
  docker rm -f linkedin-pilot-api-verify "$PILOT_CONTAINER" 2>/dev/null || true
  timeout "$D_COMPOSE" $COMPOSE --profile celery-linkedin up -d worker-linkedin 2>/dev/null || true
}
trap pilot_cleanup EXIT INT TERM

EXPECTED_SHA="${PILOT_EXPECTED_GIT_SHA:-$(git rev-parse HEAD)}"
log "Preflight git_sha=${EXPECTED_SHA}"
docker exec linkedin-scraper-worker-linkedin grep -q rejected_keyword_serp \
  /app/app/modules/collection/services/collector.py \
  || { log "ERROR worker image missing metrics fixes"; exit 20; }

GB_JOBS_BEFORE=$(mongo_eval "print(db.getSiblingDB('${PILOT_DB}').jobs.countDocuments({source:'linkedin',search_country_code:'GB'}))")
log "UK jobs preserved before batch gb_pilot_jobs=${GB_JOBS_BEFORE}"

log "Preflight: cancel stale running linkedin runs only"
mongo_eval "const dbp=db.getSiblingDB('${PILOT_DB}');
dbp.collection_runs.updateMany(
  {source:'linkedin',status:'running'},
  { \$set:{status:'cancelled',error_summary:'multi_batch_pre_reset',finished_at:new Date()}}
);
dbp.collection_targets.updateMany({source:'linkedin'},{ \$set:{enabled:false,lock_owner:null,locked_until:null}});"

docker stop linkedin-scraper-worker-linkedin 2>/dev/null || true
docker rm -f "$PILOT_CONTAINER" 2>/dev/null || true

log "Start isolated pilot worker (steady worker stopped for queue isolation)"
timeout "$D_COMPOSE" $COMPOSE --profile celery-linkedin run -d --name "$PILOT_CONTAINER" \
  -e ALLOW_LIVE_LINKEDIN_COLLECTION=true \
  -e CELERY_ALLOW_LINKEDIN_TASKS=true \
  -e CELERY_WORKER_MONGO_DB_NAME="$PILOT_DB" \
  -e CELERY_DISPATCH_SOURCE_ALLOWLIST=linkedin \
  -e CELERY_TASK_MAX_RETRIES=0 \
  -e LINKEDIN_MAX_DETAIL_OPENS_PER_RUN=25 \
  -e LINKEDIN_MAX_SEARCH_PAGES_PER_RUN=3 \
  worker-linkedin

ready_ok=0
for i in $(seq 1 60); do
  if docker logs "$PILOT_CONTAINER" 2>&1 | grep -qE "linkedin-worker@[^ ]+ ready\.'"; then
    ready_ok=1
    break
  fi
  sleep 3
done
[ "$ready_ok" -eq 1 ] || { log "ERROR pilot worker not ready"; exit 21; }

BATCH_MARK=$(date -u +%Y-%m-%dT%H:%M:%SZ)
RESULTS_FILE="/tmp/multi_country_pilot_$(date -u +%Y%m%dT%H%M%SZ).jsonl"
: >"$RESULTS_FILE"

for idx in "${!COUNTRIES[@]}"; do
  CC="${COUNTRIES[$idx]}"
  CN="${COUNTRY_NAMES[$idx]}"
  log "=== Country ${CC} (${CN}) dispatch max_jobs=${MAX_JOBS_PER_COUNTRY} ==="

  mongo_eval "const dbp=db.getSiblingDB('${PILOT_DB}');
dbp.collection_targets.updateMany({source:'linkedin'},{ \$set:{enabled:false}});
dbp.collection_targets.updateOne(
  {source:'linkedin',country_code:'${CC}',keyword:'${KEYWORD}',search_location:''},
  { \$set:{enabled:true,max_jobs_per_run:${MAX_JOBS_PER_COUNTRY},priority:300,country_name:'${CN}',lock_owner:null,locked_until:null}},
  {upsert:true}
);"

  DISPATCH_MARK=$(date -u +%Y-%m-%dT%H:%M:%SZ)
  DISPATCH_OUT=$(timeout "$D_DISPATCH" docker exec -w /app \
    -e CELERY_WORKER_MONGO_DB_NAME="$PILOT_DB" \
    -e CELERY_ALLOW_LINKEDIN_TASKS=true \
    -e ALLOW_LIVE_LINKEDIN_COLLECTION=true \
  "$PILOT_CONTAINER" python -m app.cli.celery_ops pilot-dispatch-once \
    --source linkedin --country-code "$CC" --keyword "$KEYWORD" --search-location "" --max-jobs "$MAX_JOBS_PER_COUNTRY")
  echo "$DISPATCH_OUT"
  TASK_ID=$(echo "$DISPATCH_OUT" | python3 -c "import sys,json; print(json.load(sys.stdin).get('task_id',''))" 2>/dev/null || true)
  log "dispatched task_id=${TASK_ID} mark=${DISPATCH_MARK}"

  RUN_ID=""
  RUN_STATUS="none"
  NEW_RUN_SEEN=0
  RUNNING_POLLS=0
  COUNTRY_START=$(date +%s)

  for poll in $(seq 1 "$COUNTRY_POLL_MAX"); do
    NOW=$(date +%s)
    if [ $((NOW - COUNTRY_START)) -ge "$COUNTRY_WALL_SEC" ]; then
      log "Country ${CC} wall timeout ${COUNTRY_WALL_SEC}s"
      mongo_eval "const dbp=db.getSiblingDB('${PILOT_DB}');
const r=dbp.collection_runs.find({source:'linkedin',country_code:'${CC}'}).sort({started_at:-1}).limit(1).toArray()[0];
if(r && r.status==='running'){ dbp.collection_runs.updateOne({run_id:r.run_id},{ \$set:{status:'cancelled',error_summary:'multi_country_wall_timeout',finished_at:new Date()}}); }"
      RUN_STATUS="wall_timeout"
      break
    fi

    RUN_LINE=$(mongo_eval "
const dbp=db.getSiblingDB('${PILOT_DB}');
const runs=dbp.collection_runs.find({source:'linkedin',country_code:'${CC}'}).sort({started_at:-1}).toArray();
const r=runs.find(x=>x.started_at && x.started_at.toISOString()>'${DISPATCH_MARK}') || null;
if(!r){print('none|none|none|0|0|none|none');}
else{
  print([r.status,r.run_id,r.started_at.toISOString(),r.collected_count||0,r.created_count||0,r.error_summary||'',r.task_id||''].join('|'));
}")
    RUN_STATUS=$(echo "$RUN_LINE" | cut -d'|' -f1)
    RUN_ID=$(echo "$RUN_LINE" | cut -d'|' -f2)
    RUN_START=$(echo "$RUN_LINE" | cut -d'|' -f3)
    COLL=$(echo "$RUN_LINE" | cut -d'|' -f4)
    CREATED=$(echo "$RUN_LINE" | cut -d'|' -f5)
    ERR=$(echo "$RUN_LINE" | cut -d'|' -f6)

    if [ "$RUN_START" != "none" ] && [[ "$RUN_START" > "$DISPATCH_MARK" ]]; then
      NEW_RUN_SEEN=1
    fi

    log "poll=${poll} cc=${CC} task=${TASK_ID} run=${RUN_ID} status=${RUN_STATUS} collected=${COLL} created=${CREATED}"

    if [ "$NEW_RUN_SEEN" -eq 1 ]; then
      if [ "$RUN_STATUS" = "completed" ] || [ "$RUN_STATUS" = "failed" ] || [ "$RUN_STATUS" = "cancelled" ]; then
        break
      fi
      if [ "$RUN_STATUS" = "running" ]; then
        RUNNING_POLLS=$((RUNNING_POLLS + 1))
        if [ "$RUNNING_POLLS" -ge "$STALL_RUNNING_POLLS" ]; then
          log "Country ${CC} stall revoke task_id=${TASK_ID}"
          [ -n "$TASK_ID" ] && docker exec "$PILOT_CONTAINER" celery -A app.workers.celery_app control revoke --terminate "$TASK_ID" 2>/dev/null || true
          [ -n "$RUN_ID" ] && [ "$RUN_ID" != "none" ] && mongo_eval "db.getSiblingDB('${PILOT_DB}').collection_runs.updateOne({run_id:'${RUN_ID}'},{ \$set:{status:'cancelled',error_summary:'multi_country_stall',finished_at:new Date()}})"
          RUN_STATUS="stall_cancelled"
          break
        fi
      fi
    fi

    if [ "$NEW_RUN_SEEN" -eq 0 ] && [ "$poll" -ge 24 ]; then
      RUN_STATUS="no_new_run"
      break
    fi
    sleep "$POLL_SLEEP"
  done

  JOBS_CC=$(mongo_eval "print(db.getSiblingDB('${PILOT_DB}').jobs.countDocuments({source:'linkedin',search_country_code:'${CC}'}))")
  echo "{\"country\":\"${CC}\",\"task_id\":\"${TASK_ID}\",\"run_id\":\"${RUN_ID}\",\"status\":\"${RUN_STATUS}\",\"jobs_in_pilot_db\":${JOBS_CC},\"dispatch_mark\":\"${DISPATCH_MARK}\"}" >>"$RESULTS_FILE"
  log "Country ${CC} terminal status=${RUN_STATUS} run_id=${RUN_ID} jobs=${JOBS_CC}"
done

GB_JOBS_AFTER=$(mongo_eval "print(db.getSiblingDB('${PILOT_DB}').jobs.countDocuments({source:'linkedin',search_country_code:'GB'}))")
log "UK jobs after batch gb_before=${GB_JOBS_BEFORE} gb_after=${GB_JOBS_AFTER}"

log "Pilot API spot-check"
docker rm -f linkedin-pilot-api-verify 2>/dev/null || true
timeout "$D_COMPOSE" $COMPOSE run -d --name linkedin-pilot-api-verify \
  -p 127.0.0.1:18097:8000 -e MONGO_DB_NAME="$PILOT_DB" api
for i in $(seq 1 30); do
  curl -sf http://127.0.0.1:18097/health/live >/dev/null && break
  sleep 2
done
for CC in "${COUNTRIES[@]}"; do
  curl -sf "http://127.0.0.1:18097/api/v1/jobs?source=linkedin&country_code=${CC}&page_size=3" \
    | python3 -c "import sys,json; d=json.load(sys.stdin); print('API', '${CC}', 'total=', d.get('data',{}).get('total',0))" || echo "API_FAIL ${CC}"
done

log "Batch result lines:"
cat "$RESULTS_FILE"
mongo_eval "printjson({
  batch_mark: '${BATCH_MARK}',
  total_linkedin_pilot_jobs: db.getSiblingDB('${PILOT_DB}').jobs.countDocuments({source:'linkedin'}),
  gb_jobs_before: ${GB_JOBS_BEFORE},
  gb_jobs_after: ${GB_JOBS_AFTER},
});"

trap - EXIT INT TERM
pilot_cleanup
log "Multi-country batch finished"
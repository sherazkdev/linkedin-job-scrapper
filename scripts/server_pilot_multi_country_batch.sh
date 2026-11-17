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

# Manifest-aligned country-wide Software Engineer targets (country-wide search_location "")
COUNTRIES=(PK GB US DE AE)
COUNTRY_NAMES=("Pakistan" "United Kingdom" "United States" "Germany" "United Arab Emirates")

D_MONGO=45
D_COMPOSE=180

MONGO_USER=$(timeout "$D_MONGO" docker exec linkedin-scraper-mongodb printenv MONGO_INITDB_ROOT_USERNAME)
MONGO_PASS=$(timeout "$D_MONGO" docker exec linkedin-scraper-mongodb printenv MONGO_INITDB_ROOT_PASSWORD)

log() { echo "[$(date -u +%Y-%m-%dT%H:%M:%SZ)] $*" >&2; }

mongo_eval() {
  timeout "$D_MONGO" docker exec linkedin-scraper-mongodb mongosh -u "$MONGO_USER" -p "$MONGO_PASS" \
    --authenticationDatabase admin --quiet --eval "$1"
}

pilot_cleanup() {
  mongo_eval "db.getSiblingDB('${PILOT_DB}').collection_targets.updateMany(
    { source: 'linkedin' }, { \$set: { enabled: false, lock_owner: null, locked_until: null } }
  )" || true
  docker rm -f linkedin-pilot-api-verify "$PILOT_CONTAINER" 2>/dev/null || true
  timeout "$D_COMPOSE" $COMPOSE --profile celery-linkedin up -d worker-linkedin 2>/dev/null || true
}
trap pilot_cleanup EXIT INT TERM

log "Preflight: disable all linkedin pilot targets"
mongo_eval "const dbp=db.getSiblingDB('${PILOT_DB}');
dbp.collection_targets.updateMany({source:'linkedin'},{ \$set:{enabled:false,lock_owner:null,locked_until:null}});
dbp.collection_runs.updateMany({source:'linkedin',status:'running'},{ \$set:{status:'cancelled',error_summary:'multi_batch_pre_reset',finished_at:new Date()}});"

docker stop linkedin-scraper-worker-linkedin 2>/dev/null || true
docker rm -f "$PILOT_CONTAINER" 2>/dev/null || true

log "Start isolated pilot worker"
timeout "$D_COMPOSE" $COMPOSE --profile celery-linkedin run -d --name "$PILOT_CONTAINER" \
  -e ALLOW_LIVE_LINKEDIN_COLLECTION=true \
  -e CELERY_ALLOW_LINKEDIN_TASKS=true \
  -e CELERY_WORKER_MONGO_DB_NAME="$PILOT_DB" \
  -e CELERY_DISPATCH_SOURCE_ALLOWLIST=linkedin \
  -e LINKEDIN_MAX_DETAIL_OPENS_PER_RUN=25 \
  -e LINKEDIN_MAX_SEARCH_PAGES_PER_RUN=3 \
  worker-linkedin

for i in $(seq 1 60); do
  docker logs "$PILOT_CONTAINER" 2>&1 | grep -qE "linkedin-worker@[^ ]+ ready\.'" && break
  sleep 3
done

for idx in "${!COUNTRIES[@]}"; do
  CC="${COUNTRIES[$idx]}"
  CN="${COUNTRY_NAMES[$idx]}"
  log "=== Country ${CC} (${CN}) max_jobs=${MAX_JOBS_PER_COUNTRY} ==="
  mongo_eval "const dbp=db.getSiblingDB('${PILOT_DB}');
dbp.collection_targets.updateMany({source:'linkedin'},{ \$set:{enabled:false}});
dbp.collection_targets.updateOne(
  {source:'linkedin',country_code:'${CC}',keyword:'${KEYWORD}',search_location:''},
  { \$set:{enabled:true,max_jobs_per_run:${MAX_JOBS_PER_COUNTRY},priority:300,country_name:'${CN}',lock_owner:null,locked_until:null}},
  {upsert:true}
);"
  MARK=$(date -u +%Y-%m-%dT%H:%M:%SZ)
  docker exec -w /app -e CELERY_WORKER_MONGO_DB_NAME="$PILOT_DB" -e CELERY_ALLOW_LINKEDIN_TASKS=true \
    -e ALLOW_LIVE_LINKEDIN_COLLECTION=true "$PILOT_CONTAINER" \
    python -m app.cli.celery_ops pilot-dispatch-once \
    --source linkedin --country-code "$CC" --keyword "$KEYWORD" --search-location "" --max-jobs "$MAX_JOBS_PER_COUNTRY"

  for poll in $(seq 1 90); do
    LINE=$(mongo_eval "
const r=db.getSiblingDB('${PILOT_DB}').collection_runs.find({source:'linkedin',country_code:'${CC}'}).sort({started_at:-1}).limit(1).toArray()[0];
if(!r){print('none|none|none|0');}else{print([r.status,r.run_id,r.started_at&&r.started_at.toISOString(),r.created_count||0,r.error_summary||''].join('|'));}
")
    ST=$(echo "$LINE" | cut -d'|' -f1)
    sleep 4
    [ "$ST" = "completed" ] || [ "$ST" = "failed" ] || [ "$ST" = "cancelled" ] && break
  done
  JOBS=$(mongo_eval "print(db.getSiblingDB('${PILOT_DB}').jobs.countDocuments({source:'linkedin',search_country_code:'${CC}'}))")
  log "Country ${CC} done status=$ST pilot_jobs_for_country=$JOBS"
done

log "Pilot API spot-check"
docker rm -f linkedin-pilot-api-verify 2>/dev/null || true
$COMPOSE run -d --name linkedin-pilot-api-verify -p 127.0.0.1:18097:8000 -e MONGO_DB_NAME="$PILOT_DB" api
sleep 5
for CC in "${COUNTRIES[@]}"; do
  curl -sf "http://127.0.0.1:18097/api/v1/jobs?source=linkedin&country_code=${CC}&page_size=3" | python3 -c "import sys,json; d=json.load(sys.stdin); print('${CC}', d.get('data',{}).get('total',0))" || true
done

mongo_eval "printjson({ total_linkedin_pilot_jobs: db.getSiblingDB('${PILOT_DB}').jobs.countDocuments({source:'linkedin'}) });"

trap - EXIT
pilot_cleanup
log "Multi-country batch finished"
#!/usr/bin/env bash
set -euo pipefail
APP_DIR=/var/www/linkedin-job-scrapper
cd "$APP_DIR"
COMPOSE="docker compose -f compose.yaml -f compose.contabo-vps.yaml -p linkedin-scraper"
REASON="${1:-manual_stop}"
PILOT_DB=global_jobs_pilot
PROD_DB=global_jobs
MONGO_USER=$(docker exec linkedin-scraper-mongodb printenv MONGO_INITDB_ROOT_USERNAME)
MONGO_PASS=$(docker exec linkedin-scraper-mongodb printenv MONGO_INITDB_ROOT_PASSWORD)

echo "STEP stop_beat"
docker stop linkedin-scraper-beat 2>/dev/null || true
docker rm -f linkedin-scraper-beat 2>/dev/null || true

echo "STEP disable_linkedin_targets"
docker exec linkedin-scraper-mongodb mongosh -u "$MONGO_USER" -p "$MONGO_PASS" \
  --authenticationDatabase admin --quiet --eval "
db.getSiblingDB('${PILOT_DB}').collection_targets.updateMany(
  {source:'linkedin'}, {\$set:{enabled:false}}
);"

echo "STEP restore_steady_worker"
$COMPOSE --profile celery-linkedin up -d --force-recreate worker-linkedin

STAMP=$(date -u +%Y%m%dT%H%M%SZ)
mkdir -p evidence/wave1_observation
docker exec linkedin-scraper-worker-linkedin python -m app.cli.wave1_ops status \
  >"evidence/wave1_observation/wave1_final_${STAMP}.json" 2>/dev/null || true
docker exec linkedin-scraper-mongodb mongosh -u "$MONGO_USER" -p "$MONGO_PASS" \
  --authenticationDatabase admin --quiet --eval "
printjson({
  reason: '${REASON}',
  production_jobs: db.getSiblingDB('${PROD_DB}').jobs.countDocuments({}),
  pilot_linkedin_jobs: db.getSiblingDB('${PILOT_DB}').jobs.countDocuments({source:'linkedin'}),
  enabled_linkedin_targets: db.getSiblingDB('${PILOT_DB}').collection_targets.countDocuments({source:'linkedin',enabled:true})
});
" >>"evidence/wave1_observation/wave1_final_${STAMP}.json"

echo "WAVE1_STOPPED reason=${REASON}"
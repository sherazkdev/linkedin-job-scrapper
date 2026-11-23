#!/usr/bin/env bash
set -euo pipefail
APP_DIR=/var/www/linkedin-job-scrapper
cd "$APP_DIR"
# shellcheck source=lib_compose.sh
. scripts/lib_compose.sh
PILOT_DB=global_jobs_pilot
PROD_DB=global_jobs
MONGO_USER=$(docker exec linkedin-scraper-mongodb printenv MONGO_INITDB_ROOT_USERNAME)
MONGO_PASS=$(docker exec linkedin-scraper-mongodb printenv MONGO_INITDB_ROOT_PASSWORD)

mongo_eval() {
  docker exec linkedin-scraper-mongodb mongosh -u "$MONGO_USER" -p "$MONGO_PASS" \
    --authenticationDatabase admin --quiet --eval "$1"
}

echo "STEP production_db_baseline"
mongo_eval "printjson({production_jobs: db.getSiblingDB('${PROD_DB}').jobs.countDocuments({}), pilot_jobs: db.getSiblingDB('${PILOT_DB}').jobs.countDocuments({source:'linkedin'})})"

echo "STEP api_db_isolation"
API_DB=$(docker exec linkedin-scraper-api printenv MONGO_DB_NAME)
[ "$API_DB" = "$PROD_DB" ] || { echo "ERROR api must use ${PROD_DB}"; exit 2; }

echo "STEP beat_worker_preflight"
"${COMPOSE[@]}" run --rm --no-deps worker-linkedin python -m app.cli.wave1_ops preflight

echo "STEP steady_worker_must_not_consume_linkedin"
if docker ps --format '{{.Names}}' | grep -qx linkedin-scraper-worker; then
  LIVE=$(docker exec linkedin-scraper-worker printenv CELERY_ALLOW_LINKEDIN_TASKS 2>/dev/null || echo true)
  [ "${LIVE}" = "false" ] || { echo "ERROR stop generic worker before wave1"; exit 3; }
fi

echo "WAVE1_PREFLIGHT_OK"
#!/usr/bin/env bash
# Production publication safety: DB check, validate, backup, dry-run (no apply).
set -euo pipefail
APP_DIR=/var/www/linkedin-job-scrapper
cd "$APP_DIR"
mkdir -p evidence/promotion_backups
PILOT_DB=global_jobs_pilot
PROD_DB=global_jobs
MONGO_USER=$(docker exec linkedin-scraper-mongodb printenv MONGO_INITDB_ROOT_USERNAME)
MONGO_PASS=$(docker exec linkedin-scraper-mongodb printenv MONGO_INITDB_ROOT_PASSWORD)

echo "STEP wave1_unchanged"
docker ps --format '{{.Names}}' | grep -qx linkedin-scraper-beat
docker ps --format '{{.Names}}' | grep -qx linkedin-scraper-worker-linkedin

echo "STEP production_api_db"
docker exec linkedin-scraper-api printenv MONGO_DB_NAME | grep -qx "$PROD_DB"

echo "STEP pilot_api_up"
bash scripts/server_pilot_api_up.sh

echo "STEP mongodb_counts"
docker exec linkedin-scraper-mongodb mongosh -u "$MONGO_USER" -p "$MONGO_PASS" \
  --authenticationDatabase admin --quiet --eval "
printjson({
  pilot_linkedin: db.getSiblingDB('${PILOT_DB}').jobs.countDocuments({source:'linkedin',data_provenance:'live_api_verified',status:'active'}),
  production_total: db.getSiblingDB('${PROD_DB}').jobs.countDocuments({}),
  production_linkedin_live: db.getSiblingDB('${PROD_DB}').jobs.countDocuments({source:'linkedin',data_provenance:'live_api_verified'})
});
"

echo "STEP promote_validate"
docker exec linkedin-scraper-api-pilot python -m app.cli.promote_pilot validate

echo "STEP promote_preflight"
docker exec linkedin-scraper-api-pilot python -m app.cli.promote_pilot preflight

echo "STEP promote_dry_run"
docker exec linkedin-scraper-api-pilot python -m app.cli.promote_pilot dry-run

echo "STEP promotion_backup"
docker exec linkedin-scraper-api-pilot python -m app.cli.promote_pilot backup

echo "PROMOTION_SAFETY_OK"
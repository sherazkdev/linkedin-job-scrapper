#!/usr/bin/env bash
# Production publication safety: DB check, validate, backup, dry-run (no apply).
set -euo pipefail
APP_DIR=/var/www/linkedin-job-scrapper
cd "$APP_DIR"
mkdir -p evidence/promotion_backups evidence/publication_readiness
chown -R 1000:1000 evidence/promotion_backups evidence/publication_readiness 2>/dev/null \
  || chmod 1777 evidence/promotion_backups evidence/publication_readiness
PILOT_DB=global_jobs_pilot
PROD_DB=global_jobs
WAVE1_START_ISO="${WAVE1_START_ISO:-2026-11-17T06:30:30+00:00}"
MONGO_USER=$(docker exec linkedin-scraper-mongodb printenv MONGO_INITDB_ROOT_USERNAME)
MONGO_PASS=$(docker exec linkedin-scraper-mongodb printenv MONGO_INITDB_ROOT_PASSWORD)

echo "STEP wave1_stopped_for_publication"
if docker ps --format '{{.Names}}' | grep -qx linkedin-scraper-beat; then
  echo "ERROR beat_must_be_stopped_before_publication"
  exit 2
fi
docker ps --format '{{.Names}}' | grep -qx linkedin-scraper-worker-linkedin
LIVE=$(docker exec linkedin-scraper-worker-linkedin printenv ALLOW_LIVE_LINKEDIN_COLLECTION 2>/dev/null || echo unset)
CELERY_LI=$(docker exec linkedin-scraper-worker-linkedin printenv CELERY_ALLOW_LINKEDIN_TASKS 2>/dev/null || echo unset)
case "${LIVE,,}" in false) ;; *) echo "ERROR worker_ALLOW_LIVE_LINKEDIN_COLLECTION_not_false got=${LIVE}"; exit 2 ;; esac
case "${CELERY_LI,,}" in false|unset|"") ;; *) echo "ERROR worker_CELERY_ALLOW_LINKEDIN_not_false got=${CELERY_LI}"; exit 2 ;; esac
ENABLED=$(docker exec linkedin-scraper-mongodb mongosh -u "$MONGO_USER" -p "$MONGO_PASS" \
  --authenticationDatabase admin --quiet --eval \
  "db.getSiblingDB('${PILOT_DB}').collection_targets.countDocuments({source:'linkedin',enabled:true})")
if [ "${ENABLED:-0}" -ne 0 ]; then
  echo "ERROR linkedin_enabled_targets_expected_0 got=${ENABLED}"
  exit 2
fi
PILOT_LI=$(docker exec linkedin-scraper-mongodb mongosh -u "$MONGO_USER" -p "$MONGO_PASS" \
  --authenticationDatabase admin --quiet --eval \
  "db.getSiblingDB('${PILOT_DB}').jobs.countDocuments({source:'linkedin',data_provenance:'live_api_verified',status:'active'})")
if [ "${PILOT_LI:-0}" -lt 1 ]; then
  echo "ERROR no_eligible_pilot_jobs got=${PILOT_LI}"
  exit 2
fi
echo "wave1_stopped_ok pilot_live_verified_jobs=${PILOT_LI} wave1_start=${WAVE1_START_ISO}"

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
#!/usr/bin/env bash
# Post-deploy verification: pilot job count, caps, dispatch dry-run, rollback markers.
set -euo pipefail
APP_DIR=/var/www/linkedin-job-scrapper
cd "$APP_DIR"
COMPOSE="docker compose -f compose.yaml -f compose.contabo-vps.yaml -p linkedin-scraper"
PILOT_DB=global_jobs_pilot
MONGO_USER=$(docker exec linkedin-scraper-mongodb printenv MONGO_INITDB_ROOT_USERNAME)
MONGO_PASS=$(docker exec linkedin-scraper-mongodb printenv MONGO_INITDB_ROOT_PASSWORD)

mongo_eval() {
  docker exec linkedin-scraper-mongodb mongosh -u "$MONGO_USER" -p "$MONGO_PASS" \
    --authenticationDatabase admin --quiet --eval "$1"
}

echo "STEP pilot_linkedin_jobs"
JOBS=$(mongo_eval "db.getSiblingDB('${PILOT_DB}').jobs.countDocuments({source:'linkedin'})")
echo "pilot_linkedin_jobs=${JOBS}"
[ "$JOBS" -ge 10 ] || { echo "ERROR expected_at_least_10_pilot_jobs"; exit 31; }

echo "STEP linkedin_targets_disabled"
ENABLED=$(mongo_eval "db.getSiblingDB('${PILOT_DB}').collection_targets.countDocuments({source:'linkedin',enabled:true})")
echo "linkedin_enabled_targets=${ENABLED}"
[ "$ENABLED" -eq 0 ] || { echo "ERROR linkedin_targets_must_stay_disabled"; exit 32; }

echo "STEP worker_env_gates"
docker exec linkedin-scraper-worker-linkedin printenv ALLOW_LIVE_LINKEDIN_COLLECTION | tee /tmp/allow_live.txt
docker exec linkedin-scraper-worker-linkedin printenv CELERY_ALLOW_LINKEDIN_TASKS | tee /tmp/allow_celery.txt
grep -qx false /tmp/allow_live.txt
grep -qx false /tmp/allow_celery.txt

echo "STEP dispatch_once_offline"
docker exec linkedin-scraper-worker-linkedin python -m app.cli.celery_ops dispatch-once

echo "STEP scheduling_ops"
docker exec linkedin-scraper-worker-linkedin python -m app.cli.scheduling_ops | head -c 1200
echo ""

echo "STEP queue_depth"
docker exec linkedin-scraper-worker-linkedin python -m app.cli.celery_ops stats

echo "PHASE3_VERIFY_OK"
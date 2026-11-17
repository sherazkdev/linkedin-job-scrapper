#!/usr/bin/env bash
# Phase 6: align VPS to origin/main, rebuild app images, verify counts (no Beat/live).
set -euo pipefail
APP_DIR=/var/www/linkedin-job-scrapper
cd "$APP_DIR"
COMPOSE="docker compose -f compose.yaml -f compose.contabo-vps.yaml -p linkedin-scraper"
PILOT_COMPOSE="docker compose -f compose.yaml -f compose.contabo-vps.yaml -f compose.contabo-pilot-api.yaml -p linkedin-scraper"
TARGET_SHA="${1:-}"

echo "STEP git_fetch"
git fetch origin main
ORIGIN_SHA=$(git rev-parse origin/main)
echo "origin_main=${ORIGIN_SHA}"

echo "STEP stash_review_only"
git stash list | head -5 || true
echo "NOTE not auto-applying stash (pre-phase4-pull may differ from origin)"

CURRENT=$(git rev-parse HEAD)
if [ -n "$TARGET_SHA" ]; then
  if ! git cat-file -t "${TARGET_SHA}" >/dev/null 2>&1; then
    git fetch origin main
  fi
  if [ "$CURRENT" != "$(git rev-parse "${TARGET_SHA}^{commit}")" ]; then
    git merge --ff-only "${TARGET_SHA}^{commit}" || git pull --ff-only origin main
  fi
elif [ "$CURRENT" != "$ORIGIN_SHA" ]; then
  git pull --ff-only origin main
fi
DEPLOYED=$(git rev-parse HEAD)
echo "DEPLOYED_SHA=${DEPLOYED}"
echo "DEPLOYED_SHORT=$(git rev-parse --short HEAD)"

echo "STEP rebuild_services"
$COMPOSE build api worker-linkedin
$COMPOSE up -d api worker-linkedin
$PILOT_COMPOSE build api-pilot
$PILOT_COMPOSE up -d api-pilot

echo "STEP gates"
test "$(docker ps --format '{{.Names}}' | grep -c '^linkedin-scraper-beat$' || true)" -eq 0
docker exec linkedin-scraper-worker-linkedin printenv ALLOW_LIVE_LINKEDIN_COLLECTION | grep -qx false
docker exec linkedin-scraper-api printenv MONGO_DB_NAME | grep -qx global_jobs
docker exec linkedin-scraper-api-pilot printenv MONGO_DB_NAME | grep -qx global_jobs_pilot

MONGO_USER=$(docker exec linkedin-scraper-mongodb printenv MONGO_INITDB_ROOT_USERNAME)
MONGO_PASS=$(docker exec linkedin-scraper-mongodb printenv MONGO_INITDB_ROOT_PASSWORD)
docker exec linkedin-scraper-mongodb mongosh -u "$MONGO_USER" -p "$MONGO_PASS" \
  --authenticationDatabase admin --quiet --eval "
const v={source:'linkedin',data_provenance:'live_api_verified',status:'active'};
printjson({
  pilot: db.getSiblingDB('global_jobs_pilot').jobs.countDocuments(v),
  production: db.getSiblingDB('global_jobs').jobs.countDocuments(v)
});
"

echo "PHASE6_DEPLOY_OK sha=${DEPLOYED}"
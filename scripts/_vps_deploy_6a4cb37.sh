#!/usr/bin/env bash
set -euo pipefail
APP_DIR=/var/www/linkedin-job-scrapper
TARGET_SHA=6a4cb3793ec6bc2c063b2d5c522099597aeb074e
cd "$APP_DIR"
DIRTY=$(git status --porcelain | wc -l | tr -d ' ')
STASHED=0
if [ "${DIRTY}" -gt 0 ]; then
  git stash push -m "pre-deploy-6a4cb37-$(date -u +%Y%m%dT%H%M%SZ)" --include-untracked || true
  STASHED=1
fi
git fetch origin
git checkout -f main
git reset --hard "${TARGET_SHA}"
source scripts/lib_compose.sh
WORKER_COMPOSE=(docker compose -f compose.yaml -f compose.contabo-vps.yaml -f compose.contabo-pilot.yaml -p linkedin-scraper --profile celery-linkedin)
"${COMPOSE[@]}" build api api-pilot
"${COMPOSE[@]}" up -d --no-deps api api-pilot
"${WORKER_COMPOSE[@]}" build worker-linkedin
"${WORKER_COMPOSE[@]}" up -d --no-deps worker-linkedin
MU=$(docker exec linkedin-scraper-mongodb printenv MONGO_INITDB_ROOT_USERNAME)
MP=$(docker exec linkedin-scraper-mongodb printenv MONGO_INITDB_ROOT_PASSWORD)
docker exec linkedin-scraper-mongodb mongosh -u "$MU" -p "$MP" --authenticationDatabase admin --quiet --eval \
  'printjson({production:db.getSiblingDB("global_jobs").jobs.countDocuments({}),pilot:db.getSiblingDB("global_jobs_pilot").jobs.countDocuments({})})'
curl -fsS https://jobsfinder.batteryanimation2.com/health/live
curl -fsS https://jobsfinder.batteryanimation2.com/api/v1/jobs/stats | head -c 200
echo
docker exec linkedin-scraper-worker-linkedin printenv ALLOW_LIVE_LINKEDIN_COLLECTION
docker ps --format '{{.Names}}' | grep -c '^linkedin-scraper-beat$' || true
[ "${STASHED}" -eq 1 ] && git stash pop || true
git rev-parse HEAD
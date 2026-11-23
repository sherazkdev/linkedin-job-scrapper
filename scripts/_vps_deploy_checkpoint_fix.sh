#!/usr/bin/env bash
# Code-only deploy — API + worker image; collection flags stay off; no live pilot.
set -euo pipefail
APP_DIR=/var/www/linkedin-job-scrapper
TARGET_SHA="${1:-}"
STAMP=$(date -u +%Y%m%dT%H%M%SZ)
cd "$APP_DIR"
log() { echo "[$(date -u +%H:%M:%SZ)] $*"; }

DIRTY=$(git status --porcelain | wc -l | tr -d ' ')
STASHED=0
if [ "${DIRTY}" -gt 0 ]; then
  git stash push -m "pre-checkpoint-deploy-${STAMP}" --include-untracked || true
  STASHED=1
fi

git fetch origin
if [ -n "${TARGET_SHA}" ]; then
  git checkout "${TARGET_SHA}"
else
  git pull --ff-only origin main
fi
DEPLOYED=$(git rev-parse HEAD)
log "deployed_sha=${DEPLOYED}"

source scripts/lib_compose.sh
WORKER_COMPOSE=(docker compose -f compose.yaml -f compose.contabo-vps.yaml -f compose.contabo-pilot.yaml -p linkedin-scraper --profile celery-linkedin)

"${COMPOSE[@]}" build api api-pilot
"${COMPOSE[@]}" up -d --no-deps api api-pilot
"${WORKER_COMPOSE[@]}" build worker-linkedin
"${WORKER_COMPOSE[@]}" up -d --no-deps worker-linkedin

MU=$(docker exec linkedin-scraper-mongodb printenv MONGO_INITDB_ROOT_USERNAME)
MP=$(docker exec linkedin-scraper-mongodb printenv MONGO_INITDB_ROOT_PASSWORD)
mongo_eval() {
  docker exec linkedin-scraper-mongodb mongosh -u "$MU" -p "$MP" --authenticationDatabase admin --quiet --eval "$1"
}
mongo_eval 'printjson({production:db.getSiblingDB("global_jobs").jobs.countDocuments({}),pilot:db.getSiblingDB("global_jobs_pilot").jobs.countDocuments({})})'

ALLOW=$(docker exec linkedin-scraper-worker-linkedin printenv ALLOW_LIVE_LINKEDIN_COLLECTION)
BEAT=$(docker ps --format '{{.Names}}' | grep -c '^linkedin-scraper-beat$' || true)
docker exec linkedin-scraper-worker-linkedin test -f /app/app/modules/collection/linkedin/checkpoint_policy.py
curl -fsS -m 20 https://jobsfinder.batteryanimation2.com/health/live
echo
log "allow_live=${ALLOW} beat=${BEAT}"

[ "${STASHED}" -eq 1 ] && git stash pop || true
log "SUCCESS sha=${DEPLOYED}"
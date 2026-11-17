#!/usr/bin/env bash
# Deploy Phase 4 publication automation code (no Beat, no live enable).
set -euo pipefail
APP_DIR=/var/www/linkedin-job-scrapper
cd "$APP_DIR"
COMPOSE="docker compose -f compose.yaml -f compose.contabo-vps.yaml -p linkedin-scraper"
git fetch origin main
git pull --ff-only origin main
echo "DEPLOYED_SHA=$(git rev-parse HEAD)"
echo "DEPLOYED_SHORT=$(git rev-parse --short HEAD)"

$COMPOSE build api worker-linkedin
$COMPOSE up -d api worker-linkedin
bash scripts/server_pilot_api_up.sh
$COMPOSE build api-pilot 2>/dev/null || $COMPOSE build api
$COMPOSE -f compose.yaml -f compose.contabo-vps.yaml -f compose.contabo-pilot-api.yaml -p linkedin-scraper up -d api-pilot

test "$(docker ps --format '{{.Names}}' | grep -c linkedin-scraper-beat || true)" -eq 0
docker exec linkedin-scraper-worker-linkedin printenv ALLOW_LIVE_LINKEDIN_COLLECTION | grep -qx false
echo "PHASE4_DEPLOY_OK"
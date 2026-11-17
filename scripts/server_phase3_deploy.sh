#!/usr/bin/env bash
# Phase 3 deploy: pull main, rebuild API + worker images only (no Beat, no live enable).
set -euo pipefail
APP_DIR=/var/www/linkedin-job-scrapper
cd "$APP_DIR"
export GIT_TERMINAL_PROMPT=0

git fetch origin main
git pull --ff-only origin main
DEPLOYED_SHA=$(git rev-parse HEAD)
DEPLOYED_SHORT=$(git rev-parse --short HEAD)
echo "DEPLOYED_SHA=${DEPLOYED_SHA}"
echo "DEPLOYED_SHORT=${DEPLOYED_SHORT}"

COMPOSE="docker compose -f compose.yaml -f compose.contabo-vps.yaml -p linkedin-scraper"
$COMPOSE build api worker-linkedin worker

# Steady-state API + worker only (no celery beat profile, no pilot live worker).
$COMPOSE up -d mongodb redis api worker-linkedin

echo "STEP verify_beat_absent"
if docker ps -a --format '{{.Names}}' | grep -q linkedin-scraper-beat; then
  echo "WARN beat container exists — stopping (Wave 0)"
  docker stop linkedin-scraper-beat 2>/dev/null || true
  docker rm -f linkedin-scraper-beat 2>/dev/null || true
fi

echo "STEP api_health"
curl -fsS "http://127.0.0.1:${LINKEDIN_SCRAPER_API_PORT:-18095}/health" | head -c 500
echo ""

echo "PHASE3_DEPLOY_OK sha=${DEPLOYED_SHORT}"
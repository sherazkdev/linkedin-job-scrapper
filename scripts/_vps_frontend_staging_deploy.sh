#!/usr/bin/env bash
set -euo pipefail
cd /var/www/linkedin-job-scrapper || exit 1
git pull --ff-only origin main
export FRONTEND_STAGING_APP_URL="${FRONTEND_STAGING_APP_URL:-http://127.0.0.1:3001}"
docker compose -f compose.yaml -f compose.contabo-vps.yaml \
  -f compose.contabo-pilot-api.yaml -f compose.contabo-alerts-flags.yaml \
  -f compose.contabo-frontend-staging.yaml -p linkedin-scraper \
  build frontend-staging
docker compose -f compose.yaml -f compose.contabo-vps.yaml \
  -f compose.contabo-pilot-api.yaml -f compose.contabo-alerts-flags.yaml \
  -f compose.contabo-frontend-staging.yaml -p linkedin-scraper \
  up -d frontend-staging
docker exec linkedin-scraper-frontend-staging wget -qO- http://127.0.0.1:3000/ >/dev/null
echo "frontend_staging_ok port=3001 loopback_only"
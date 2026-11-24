#!/usr/bin/env bash
set -euo pipefail
cd /var/www/linkedin-job-scrapper || exit 1
git pull --ff-only origin main
export FRONTEND_STAGING_PORT="${FRONTEND_STAGING_PORT:-13010}"
export FRONTEND_STAGING_APP_URL="${FRONTEND_STAGING_APP_URL:-http://127.0.0.1:${FRONTEND_STAGING_PORT}}"
COMPOSE=(docker compose -f compose.yaml -f compose.contabo-vps.yaml \
  -f compose.contabo-pilot-api.yaml -f compose.contabo-alerts-flags.yaml \
  -f compose.contabo-frontend-staging.yaml -p linkedin-scraper)
if [ "${FRONTEND_SKIP_BUILD:-0}" != "1" ]; then
  "${COMPOSE[@]}" build frontend-staging
fi
"${COMPOSE[@]}" up -d frontend-staging
docker exec linkedin-scraper-frontend-staging node -e "fetch('http://127.0.0.1:3000/').then(r=>{if(!r.ok)process.exit(1)}).catch(()=>process.exit(1))"
echo "frontend_staging_ok port=${FRONTEND_STAGING_PORT} loopback_only"
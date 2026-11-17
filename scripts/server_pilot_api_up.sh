#!/usr/bin/env bash
# Start persistent localhost-only pilot API (global_jobs_pilot). Safe alongside Wave 1 Beat.
set -euo pipefail
APP_DIR=/var/www/linkedin-job-scrapper
cd "$APP_DIR"
COMPOSE="docker compose -f compose.yaml -f compose.contabo-vps.yaml -f compose.contabo-pilot-api.yaml -p linkedin-scraper"
PORT="${LINKEDIN_SCRAPER_PILOT_API_PORT:-18097}"

$COMPOSE up -d api-pilot
for i in $(seq 1 25); do
  if curl -sf "http://127.0.0.1:${PORT}/health/live" >/dev/null; then
    echo "PILOT_API_OK http://127.0.0.1:${PORT}"
    exit 0
  fi
  sleep 2
done
echo "ERROR pilot_api_not_healthy"
exit 1
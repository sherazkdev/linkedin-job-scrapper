#!/usr/bin/env bash
# Pull latest main, rebuild worker, reconcile pilot state, one bounded live pilot.
set -euo pipefail
APP_DIR=/var/www/linkedin-job-scrapper
cd "$APP_DIR"
export GIT_TERMINAL_PROMPT=0

git pull --ff-only origin main
echo "DEPLOYED_SHA=$(git rev-parse HEAD)"
echo "DEPLOYED_SHORT=$(git rev-parse --short HEAD)"

COMPOSE="docker compose -f compose.yaml -f compose.contabo-vps.yaml -p linkedin-scraper"
$COMPOSE build worker-linkedin

bash /tmp/server_pilot_reconcile.sh 2>/dev/null || true
# reconcile from repo after upload
if [ -f ./scripts/server_pilot_reconcile.sh ]; then
  bash ./scripts/server_pilot_reconcile.sh
fi

bash ./scripts/server_pilot_retry.sh
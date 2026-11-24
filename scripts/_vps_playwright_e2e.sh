#!/usr/bin/env bash
set -euo pipefail
cd /var/www/linkedin-job-scrapper/frontend
export PLAYWRIGHT_NO_WEB_SERVER=1
export PLAYWRIGHT_BASE_URL="${PLAYWRIGHT_BASE_URL:-http://127.0.0.1:13010}"
export APP_URL="${APP_URL:-$PLAYWRIGHT_BASE_URL}"
export E2E_PILOT_READY=1
docker run --rm --network host \
  -v "/var/www/linkedin-job-scrapper/frontend:/app" \
  -w /app \
  -e PLAYWRIGHT_NO_WEB_SERVER -e PLAYWRIGHT_BASE_URL -e APP_URL -e E2E_PILOT_READY \
  mcr.microsoft.com/playwright:v1.56.1-jammy \
  bash -lc "npm ci && npx playwright install chromium && npm run test:e2e"
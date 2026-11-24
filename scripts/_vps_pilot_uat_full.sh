#!/usr/bin/env bash
set -euo pipefail
BASE="${PILOT_API_URL:-http://127.0.0.1:18097}"
PROD="${PROD_API_URL:-http://127.0.0.1:18095}"

test "$(curl -s -o /dev/null -w '%{http_code}' -X POST "$PROD/api/v1/alerts/subscribers/register")" = "404"

echo "== UAT repository pipeline =="
docker exec linkedin-scraper-api-pilot python -m app.cli.alerts_pilot_uat --run

echo "== city coverage =="
docker exec linkedin-scraper-api-pilot python -m app.cli.pilot_city_coverage

echo "== cleanup =="
docker exec linkedin-scraper-api-pilot python -m app.cli.alerts_cleanup

echo "PILOT_UAT_FULL_OK"
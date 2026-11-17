#!/usr/bin/env bash
# Read-only pilot API verification (country_code vs search_country_code).
set -euo pipefail
APP_DIR=/var/www/linkedin-job-scrapper
cd "$APP_DIR"
COMPOSE="docker compose -f compose.yaml -f compose.contabo-vps.yaml -p linkedin-scraper"
PILOT_DB=global_jobs_pilot
API_PORT=127.0.0.1:18097
COUNTRIES=(PK GB US DE AE)

docker rm -f linkedin-pilot-api-verify 2>/dev/null || true
timeout 120 $COMPOSE run -d --name linkedin-pilot-api-verify \
  -p "${API_PORT}:8000" -e MONGO_DB_NAME="$PILOT_DB" api
for i in $(seq 1 30); do
  curl -sf "http://${API_PORT}/health/live" >/dev/null && break
  sleep 2
done

echo "=== Pilot API verification ==="
for CC in "${COUNTRIES[@]}"; do
  CJ=$(curl -sf "http://${API_PORT}/api/v1/jobs?source=linkedin&country_code=${CC}&page_size=5")
  SJ=$(curl -sf "http://${API_PORT}/api/v1/jobs?source=linkedin&search_country_code=${CC}&page_size=5")
  python3 -c "import json,sys
cc='${CC}'
c=json.loads(sys.argv[1]); s=json.loads(sys.argv[2])
print(cc, 'country_code total=', c['data']['total'], 'search_country_code total=', s['data']['total'])" \
    "$CJ" "$SJ"
done

docker stop linkedin-pilot-api-verify >/dev/null 2>&1 || true
docker rm -f linkedin-pilot-api-verify >/dev/null 2>&1 || true
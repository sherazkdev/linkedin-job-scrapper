#!/usr/bin/env bash
# Read-only pilot API verification (country_code vs search_country_code).
set -euo pipefail
APP_DIR=/var/www/linkedin-job-scrapper
cd "$APP_DIR"
COMPOSE="docker compose -f compose.yaml -f compose.contabo-vps.yaml -p linkedin-scraper"
PILOT_DB=global_jobs_pilot
API_PORT=127.0.0.1:18097
COUNTRIES=(PK GB US DE AE)

if ! curl -sf "http://${API_PORT}/health/live" >/dev/null 2>&1; then
  bash scripts/server_pilot_api_up.sh
fi

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

echo "PILOT_API_VERIFY_DONE using linkedin-scraper-api-pilot"
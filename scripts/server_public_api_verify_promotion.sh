#!/usr/bin/env bash
set -euo pipefail
BASE="${PUBLIC_API_BASE:-https://jobsfinder.batteryanimation2.com}"
probe() {
  local label="$1"; shift
  local url="$1"; shift
  local code body
  code=$(curl -sS -o /tmp/api_body.json -w '%{http_code}' "$url")
  body=$(cat /tmp/api_body.json)
  total=$(python3 -c "import json; d=json.load(open('/tmp/api_body.json')); print(d.get('data',{}).get('total','?'))" 2>/dev/null || echo parse_err)
  echo "HTTP $code | total=$total | $label"
  echo "  $url"
}

probe "all_linkedin" "${BASE}/api/v1/jobs?source=linkedin&live_verified_only=true&data_provenance=live_api_verified&page_size=1"
for CC in PK GB US; do
  probe "search_${CC}" "${BASE}/api/v1/jobs?source=linkedin&search_country_code=${CC}&live_verified_only=true&data_provenance=live_api_verified&sort=posted_at_desc&page_size=3"
  probe "search_${CC}_posted7" "${BASE}/api/v1/jobs?source=linkedin&search_country_code=${CC}&live_verified_only=true&posted_within=7&sort=posted_at_desc&page_size=3"
done
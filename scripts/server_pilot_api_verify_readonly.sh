#!/usr/bin/env bash
# Read-only pilot API checks (counts, provenance, search_country_code, duplicates).
set -euo pipefail
APP_DIR=/var/www/linkedin-job-scrapper
PORT="${LINKEDIN_SCRAPER_PILOT_API_PORT:-18097}"
BASE="http://127.0.0.1:${PORT}"

curl -sf "${BASE}/health/live" >/dev/null || { echo "ERROR pilot_api_down"; exit 1; }

echo "=== totals ==="
curl -sf "${BASE}/api/v1/jobs?page_size=1" | python3 -c "import json,sys; d=json.load(sys.stdin); print('all_active', d['data']['total'])"
curl -sf "${BASE}/api/v1/jobs?source=linkedin&live_verified_only=true&page_size=1" | python3 -c "import json,sys; d=json.load(sys.stdin); print('linkedin_live_verified', d['data']['total'])"

echo "=== sample live verified (first page) ==="
curl -sf "${BASE}/api/v1/jobs?source=linkedin&live_verified_only=true&sort=posted_at_desc&page_size=5" | python3 -m json.tool | head -120

echo "=== search_country_code GB vs country_code GB ==="
curl -sf "${BASE}/api/v1/jobs?source=linkedin&search_country_code=GB&live_verified_only=true&page_size=1" | python3 -c "import json,sys; print('search_market_GB', json.load(sys.stdin)['data']['total'])"
curl -sf "${BASE}/api/v1/jobs?source=linkedin&country_code=GB&live_verified_only=true&page_size=1" | python3 -c "import json,sys; print('job_location_GB', json.load(sys.stdin)['data']['total'])"

echo "=== duplicate probe (same sourceJobId should be one doc) ==="
python3 - <<'PY'
import json, subprocess
base = f"http://127.0.0.1:{__import__('os').environ.get('LINKEDIN_SCRAPER_PILOT_API_PORT', '18097')}"
raw = subprocess.check_output(["curl", "-sf", f"{base}/api/v1/jobs?source=linkedin&live_verified_only=true&page_size=100"])
data = json.loads(raw)["data"]["items"]
ids = [j.get("source_job_id") or j.get("sourceJobId") for j in data]
print("page_items", len(data), "unique_sourceJobIds", len(set(ids)))
PY

echo "PILOT_API_VERIFY_DONE"
#!/usr/bin/env bash
# Run AFTER promotion apply (read-only). Default base URL = public production API.
set -euo pipefail
BASE="${PUBLIC_API_BASE:-https://jobsfinder.batteryanimation2.com}"
COUNTRIES=(PK GB US)

echo "BASE=${BASE}"
curl -sf "${BASE}/health/live" && echo " health_ok"

for CC in "${COUNTRIES[@]}"; do
  echo "=== search_country_code=${CC} (live verified, recent first) ==="
  curl -sfG "${BASE}/api/v1/jobs" \
    --data-urlencode "source=linkedin" \
    --data-urlencode "search_country_code=${CC}" \
    --data-urlencode "live_verified_only=true" \
    --data-urlencode "data_provenance=live_api_verified" \
    --data-urlencode "posted_within=30" \
    --data-urlencode "sort=posted_at_desc" \
    --data-urlencode "page_size=5" \
    | python3 -c "import json,sys; d=json.load(sys.stdin); print('total',d['data']['total'],'items',len(d['data']['items'])); [print(' ',i.get('sourceJobId'),i.get('posted_at'),i.get('job_url','')[:80]) for i in d['data']['items'][:5]]"
  echo "=== country_code=${CC} (compare) ==="
  curl -sfG "${BASE}/api/v1/jobs" \
    --data-urlencode "source=linkedin" \
    --data-urlencode "country_code=${CC}" \
    --data-urlencode "live_verified_only=true" \
    --data-urlencode "page_size=5" \
    | python3 -c "import json,sys; d=json.load(sys.stdin); print('total',d['data']['total'])"
done

echo "POST_PROMOTION_VERIFY_DONE"
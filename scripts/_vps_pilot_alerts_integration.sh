#!/usr/bin/env bash
# Pilot-only alerts smoke (no matching, no live LinkedIn). Cleans integration-tagged records after.
set -euo pipefail
BASE="${PILOT_API_URL:-http://127.0.0.1:18097}"
PROD_CHECK="${PROD_API_URL:-http://127.0.0.1:18095}"

echo "== production alerts disabled =="
code=$(curl -s -o /dev/null -w "%{http_code}" -X POST "$PROD_CHECK/api/v1/alerts/subscribers/register" || true)
test "$code" = "404"

echo "== pilot register =="
reg=$(curl -fsS -X POST "$BASE/api/v1/alerts/subscribers/register")
sub=$(python3 -c "import json,sys; print(json.load(sys.stdin)['subscriber_id'])" <<<"$reg")
token=$(python3 -c "import json,sys; print(json.load(sys.stdin)['bearer_token'])" <<<"$reg")
auth="Authorization: Bearer $token"

echo "== CRUD saved search =="
curl -fsS -H "$auth" -H "Content-Type: application/json" \
  -d '{"q":"engineer","country_code":"US","alerts_enabled":true}' \
  "$BASE/api/v1/alerts/searches" >/dev/null

echo "== digest preview =="
curl -fsS -H "$auth" -X POST "$BASE/api/v1/alerts/digest/preview" | head -c 500
echo

echo "== job.city coverage (pilot) =="
docker exec linkedin-scraper-api-pilot python - <<'PY'
import asyncio
from app.core.config import get_settings
from app.database.temp_database import open_database

async def main():
    s=get_settings()
    async with open_database(s.mongo_db_name) as db:
        total=await db.jobs.count_documents({})
        with_city=await db.jobs.count_documents({"city":{"$type":"string","$ne":""}})
        print({"jobs_total":total,"jobs_with_city":with_city})
asyncio.run(main())
PY

echo "== cleanup integration-tagged alert data =="
docker exec linkedin-scraper-api-pilot python -m app.cli.alerts_cleanup

echo "PILOT_ALERTS_SMOKE_OK"
#!/usr/bin/env bash
# Read-only production health monitor (no scraping, no DB writes).
set -euo pipefail
APP_DIR=/var/www/linkedin-job-scrapper
cd "$APP_DIR"
mkdir -p evidence/publication_readiness /tmp/ljs-monitor
STAMP=$(date -u +%Y%m%dT%H%M%SZ)
OUT=evidence/publication_readiness/production_monitor_${STAMP}.json
BASE="${PUBLIC_API_BASE:-https://jobsfinder.batteryanimation2.com}"
MONGO_USER=$(docker exec linkedin-scraper-mongodb printenv MONGO_INITDB_ROOT_USERNAME)
MONGO_PASS=$(docker exec linkedin-scraper-mongodb printenv MONGO_INITDB_ROOT_PASSWORD)
T=/tmp/ljs-monitor

API_HEALTH=$(curl -sf -o /dev/null -w "%{http_code}" "${BASE}/health/live" || echo 000)
curl -sf "${BASE}/api/v1/jobs?source=linkedin&live_verified_only=true&page_size=1" -o "${T}/public_jobs.json" 2>/dev/null \
  || echo '{"data":{"total":-1}}' >"${T}/public_jobs.json"
docker exec linkedin-scraper-worker-linkedin python -m app.cli.celery_ops stats >"${T}/celery.json" 2>/dev/null \
  || echo '{}' >"${T}/celery.json"
docker exec linkedin-scraper-worker-linkedin python -m app.cli.linkedin_session status >"${T}/session.json" 2>/dev/null \
  || echo '{}' >"${T}/session.json"
docker exec linkedin-scraper-api-pilot python -m app.cli.promote_pilot monitor >"${T}/promo.json" 2>/dev/null \
  || echo '{}' >"${T}/promo.json"
docker exec linkedin-scraper-mongodb mongosh -u "$MONGO_USER" -p "$MONGO_PASS" \
  --authenticationDatabase admin --quiet --eval "
const r=db.getSiblingDB('global_jobs_pilot').collection_runs;
const last=r.find({source:'linkedin',dry_run:false}).sort({started_at:-1}).limit(1).toArray();
print(JSON.stringify(last[0]||null));
" >"${T}/last_run.json"

python3 - "${T}" "${OUT}" "${STAMP}" "${BASE}" "${API_HEALTH}" <<'PY'
import json
import sys
from pathlib import Path

t, out, stamp, base, api_health = sys.argv[1:6]

def last_json_path(path: Path):
    text = path.read_text(encoding="utf-8")
    dec = json.JSONDecoder()
    idx = 0
    last = None
    while idx < len(text):
        while idx < len(text) and text[idx] not in "{[":
            idx += 1
        if idx >= len(text):
            break
        try:
            obj, end = dec.raw_decode(text, idx)
            last = obj
            idx = end
        except json.JSONDecodeError:
            idx += 1
    return last or {}

public = json.loads((Path(t) / "public_jobs.json").read_text(encoding="utf-8"))
report = {
    "generated_at": stamp,
    "public_api": {
        "base": base,
        "health_http": int(api_health or 0),
        "linkedin_total": public.get("data", {}).get("total", -1),
    },
    "celery": last_json_path(Path(t) / "celery.json"),
    "linkedin_session": last_json_path(Path(t) / "session.json"),
    "promotion_monitor": last_json_path(Path(t) / "promo.json"),
    "last_linkedin_run": json.loads((Path(t) / "last_run.json").read_text(encoding="utf-8") or "null"),
}
Path(out).write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")
print(json.dumps(report, indent=2, default=str))
PY

echo "MONITOR_FILE=$OUT"
echo "beat_running=$(docker ps --format '{{.Names}}' | grep -c '^linkedin-scraper-beat$' 2>/dev/null || echo 0)"
docker exec linkedin-scraper-mongodb mongosh -u "$MONGO_USER" -p "$MONGO_PASS" \
  --authenticationDatabase admin --quiet --eval "printjson({mongo_ping: db.adminCommand({ping:1}).ok})"
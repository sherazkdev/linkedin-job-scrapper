#!/usr/bin/env bash
set -euo pipefail
APP_DIR=/var/www/linkedin-job-scrapper
cd "$APP_DIR"
PILOT_DB=global_jobs_pilot
MONGO_USER=$(docker exec linkedin-scraper-mongodb printenv MONGO_INITDB_ROOT_USERNAME)
MONGO_PASS=$(docker exec linkedin-scraper-mongodb printenv MONGO_INITDB_ROOT_PASSWORD)
OBS_LOG=evidence/wave1_observation/observer.log
START_FILE=evidence/wave1_observation/wave1_started_at.json

mongo_eval() {
  docker exec linkedin-scraper-mongodb mongosh -u "$MONGO_USER" -p "$MONGO_PASS" \
    --authenticationDatabase admin --quiet --eval "$1"
}

log() { echo "$(date -u +%Y-%m-%dT%H:%M:%SZ) $*" | tee -a "$OBS_LOG"; }

if [ ! -f "$START_FILE" ]; then
  log "ERROR missing $START_FILE"
  exit 1
fi

END_EPOCH=$(python3 - <<'PY'
import json
from datetime import datetime, timezone
from pathlib import Path
p = Path("evidence/wave1_observation/wave1_started_at.json")
d = json.loads(p.read_text(encoding="utf-8"))
t = datetime.fromisoformat(d["started_at"].replace("Z", "+00:00"))
if t.tzinfo is None:
    t = t.replace(tzinfo=timezone.utc)
print(int(t.timestamp()) + 86400)
PY
)
AUTH_FAIL_LIMIT=3
POLL=300

log "OBSERVER_START end_epoch=$END_EPOCH"

while [ "$(date +%s)" -lt "$END_EPOCH" ]; do
  DEPTH=$(docker exec linkedin-scraper-worker-linkedin python -m app.cli.celery_ops stats 2>/dev/null | python3 -c "import sys,json; print(json.load(sys.stdin).get('queue_depth'))" 2>/dev/null || echo -1)
  STATUS=$(docker exec linkedin-scraper-worker-linkedin python -m app.cli.wave1_ops status 2>/dev/null || echo '{}')
  AUTH_FAILS=$(mongo_eval "
const t=db.getSiblingDB('${PILOT_DB}').collection_runs;
const since=new Date('$(python3 -c "import json; print(json.load(open(\"$START_FILE\"))[\"started_at\"])")');
t.countDocuments({source:'linkedin',status:'failed',started_at:{\$gte:since},\$or:[
  {error_summary:/authentication/i},
  {error_summary:/verification/i},
  {error_summary:/session/i},
  {error_summary:/access_denied/i}
]});
" 2>/dev/null || echo 0)
  MEM=$(docker stats --no-stream --format '{{.MemPerc}}' linkedin-scraper-worker-linkedin 2>/dev/null | tr -d '%' || echo 0)

  log "tick queue_depth=$DEPTH auth_fails=$AUTH_FAILS mem_pct=${MEM}"

  if [ "${AUTH_FAILS:-0}" -ge "$AUTH_FAIL_LIMIT" ]; then
    log "AUTO_STOP auth_failures=$AUTH_FAILS"
    bash scripts/server_wave1_stop.sh auth_failures
    exit 0
  fi

  MEM_INT=${MEM%.*}
  if [ "${MEM_INT:-0}" -ge 90 ] 2>/dev/null; then
    log "AUTO_STOP memory_pressure mem_pct=$MEM"
    bash scripts/server_wave1_stop.sh memory_pressure
    exit 0
  fi

  sleep "$POLL"
done

log "AUTO_STOP observation_24h_complete"
bash scripts/server_wave1_stop.sh observation_complete
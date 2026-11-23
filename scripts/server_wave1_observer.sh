#!/usr/bin/env bash
# Continuous Wave 1 guardrails: auth fails (rolling 24h), memory, cap awareness — no timed shutdown.
set -euo pipefail
APP_DIR=/var/www/linkedin-job-scrapper
cd "$APP_DIR"
PILOT_DB=global_jobs_pilot
MONGO_USER=$(docker exec linkedin-scraper-mongodb printenv MONGO_INITDB_ROOT_USERNAME)
MONGO_PASS=$(docker exec linkedin-scraper-mongodb printenv MONGO_INITDB_ROOT_PASSWORD)
OBS_LOG=evidence/wave1_observation/observer.log
AUTH_WINDOW_SECS="${WAVE1_AUTH_WINDOW_SECS:-86400}"
AUTH_FAIL_LIMIT="${WAVE1_AUTH_FAIL_LIMIT:-3}"
MEM_LIMIT_PCT="${WAVE1_MEM_LIMIT_PCT:-90}"
POLL="${WAVE1_OBSERVER_POLL_SECS:-300}"

mongo_eval() {
  docker exec linkedin-scraper-mongodb mongosh -u "$MONGO_USER" -p "$MONGO_PASS" \
    --authenticationDatabase admin --quiet --eval "$1"
}

log() { echo "$(date -u +%Y-%m-%dT%H:%M:%SZ) $*" | tee -a "$OBS_LOG"; }

log "OBSERVER_START mode=continuous auth_window_secs=${AUTH_WINDOW_SECS} poll=${POLL}"

while true; do
  if ! docker ps --format '{{.Names}}' | grep -qx linkedin-scraper-beat; then
    log "WARN beat_not_running"
    sleep "$POLL"
    continue
  fi
  if ! docker ps --format '{{.Names}}' | grep -qx linkedin-scraper-worker-linkedin; then
    log "ERROR worker_linkedin_missing"
    sleep "$POLL"
    continue
  fi

  DEPTH=$(docker exec linkedin-scraper-worker-linkedin python -m app.cli.celery_ops stats 2>/dev/null \
    | python3 -c "import sys,json; print(json.load(sys.stdin).get('queue_depth', -1))" 2>/dev/null || echo -1)
  WORKER_OK=$(docker exec linkedin-scraper-worker-linkedin python -m app.cli.celery_ops worker-ready --timeout 8 \
    >/dev/null 2>&1 && echo 1 || echo 0)
  CAP_JSON=$(mongo_eval "
const pilot=db.getSiblingDB('${PILOT_DB}');
const dayAgo=new Date(Date.now()-${AUTH_WINDOW_SECS}*1000);
const used=pilot.collection_runs.countDocuments({
  source:'linkedin', dry_run:false, started_at:{\$gte:dayAgo},
  status:{\$in:['running','completed','failed','cancelled']}
});
print(JSON.stringify({cap_used:used,cap_limit:30,cap_blocked:used>=30}));
")
  SESSION_EPOCH_FILE=evidence/wave1_observation/session_epoch_at.json
  AUTH_SINCE="new Date(Date.now()-${AUTH_WINDOW_SECS}*1000)"
  if [ -f "$SESSION_EPOCH_FILE" ]; then
    EPOCH_AT=$(python3 -c "import json,sys; d=json.load(open(sys.argv[1])); print(d.get('session_epoch_at',''))" "$SESSION_EPOCH_FILE" 2>/dev/null || true)
    if [ -n "$EPOCH_AT" ]; then
      AUTH_SINCE="new Date('${EPOCH_AT}')"
      log "AUTH_WINDOW using session_epoch_at=${EPOCH_AT}"
    fi
  fi
  AUTH_FAILS=$(mongo_eval "
const pilot=db.getSiblingDB('${PILOT_DB}');
const since=${AUTH_SINCE};
print(pilot.collection_runs.countDocuments({
  source:'linkedin',dry_run:false,started_at:{\$gte:since},status:'failed',
  \$or:[
    {error_summary:/authentication/i},{error_summary:/verification/i},
    {error_summary:/session/i},{error_summary:/access_denied/i}
  ]
}));
" 2>/dev/null || echo 0)
  MEM=$(docker stats --no-stream --format '{{.MemPerc}}' linkedin-scraper-worker-linkedin 2>/dev/null | tr -d '%' || echo 0)

  log "tick queue_depth=${DEPTH} worker_ready=${WORKER_OK} auth_fails_24h=${AUTH_FAILS} cap=${CAP_JSON} mem_pct=${MEM}"

  if [ "${AUTH_FAILS:-0}" -ge "$AUTH_FAIL_LIMIT" ]; then
    log "AUTO_STOP auth_failures_rolling_24h=${AUTH_FAILS}"
    bash scripts/server_wave1_stop.sh auth_failures
    exit 0
  fi

  MEM_INT=${MEM%.*}
  if [ "${MEM_INT:-0}" -ge "$MEM_LIMIT_PCT" ] 2>/dev/null; then
    log "AUTO_STOP memory_pressure mem_pct=${MEM}"
    bash scripts/server_wave1_stop.sh memory_pressure
    exit 0
  fi

  if [ "${DEPTH:-0}" -gt 10 ] 2>/dev/null; then
    log "WARN queue_depth_high depth=${DEPTH}"
  fi

  sleep "$POLL"
done
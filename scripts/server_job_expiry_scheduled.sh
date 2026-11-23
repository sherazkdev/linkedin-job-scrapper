#!/usr/bin/env bash
# Scheduled public listing expiry — preview, backup, gated apply (no document deletes).
set -euo pipefail
APP_DIR=/var/www/linkedin-job-scrapper
cd "$APP_DIR"
LOG_DIR=evidence/job_lifecycle
mkdir -p "$LOG_DIR" evidence/mongo_backups
STAMP=$(date -u +%Y%m%dT%H%M%SZ)
LOG="$LOG_DIR/expiry_scheduled_${STAMP}.log"
PREVIEW_JSON="$LOG_DIR/expiry_preview_${STAMP}.json"
PILOT_PREVIEW_JSON="$LOG_DIR/expiry_preview_pilot_${STAMP}.json"
PROD_PREVIEW_JSON="$LOG_DIR/expiry_preview_production_${STAMP}.json"
LOCK=/tmp/job_expiry_scheduled.lock

exec 9>"$LOCK"
if ! flock -n 9; then
  echo "[${STAMP}] SKIP overlapping job expiry" | tee -a "$LOG"
  exit 0
fi

log() { echo "[$(date -u +%Y-%m-%dT%H:%M:%SZ)] $*" | tee -a "$LOG"; }

if [ "${ALLOW_SCHEDULED_JOB_EXPIRY:-false}" != "true" ]; then
  log "SKIP ALLOW_SCHEDULED_JOB_EXPIRY not true"
  exit 0
fi

APPLY_PILOT="${JOB_EXPIRY_APPLY_PILOT:-${JOB_EXPIRY_APPLY:-false}}"
APPLY_PROD="${JOB_EXPIRY_PRODUCTION_APPLY:-false}"
MAX_AGE="${JOB_PUBLIC_LISTING_MAX_AGE_DAYS:-7}"
PILOT_DB="global_jobs_pilot"
PROD_DB="global_jobs"

log "BEGIN expiry preview max_age_days=${MAX_AGE} apply_pilot=${APPLY_PILOT} apply_production=${APPLY_PROD}"

_preview_db() {
  local db="$1"
  local container="$2"
  local out="$3"
  docker exec "$container" printenv MONGO_DB_NAME | grep -qx "$db" \
    || { log "ERROR ${container} MONGO_DB_NAME != ${db}"; return 2; }
  docker exec -e LOG_LEVEL=ERROR "$container" \
    python -m app.cli.job_lifecycle expire-preview --mongo-db "$db" >"$out" \
    || { log "ERROR preview failed db=${db}"; return 3; }
}

_preview_db "$PILOT_DB" linkedin-scraper-api-pilot "$PILOT_PREVIEW_JSON" || exit 3
_preview_db "$PROD_DB" linkedin-scraper-api "$PROD_PREVIEW_JSON" || exit 4

python3 -c "
import json
from pathlib import Path
payload = {
    'stamp': '${STAMP}',
    'max_age_days': int('${MAX_AGE}'),
    'pilot': json.loads(Path('${PILOT_PREVIEW_JSON}').read_text(encoding='utf-8')),
    'production': json.loads(Path('${PROD_PREVIEW_JSON}').read_text(encoding='utf-8')),
}
Path('${PREVIEW_JSON}').write_text(json.dumps(payload, indent=2), encoding='utf-8')
"
log "preview_saved ${PREVIEW_JSON}"

if [ "$APPLY_PILOT" != "true" ] && [ "$APPLY_PROD" != "true" ]; then
  log "DONE dry-run only (set JOB_EXPIRY_APPLY_PILOT=true and/or JOB_EXPIRY_PRODUCTION_APPLY=true)"
  exit 0
fi

if [ "$APPLY_PILOT" = "true" ]; then
  log "STEP backup_pilot"
  bash scripts/server_mongo_backup_jobs.sh "$PILOT_DB" 2>&1 | tee -a "$LOG" | grep -q BACKUP_OK \
    || { log "ERROR pilot backup failed"; exit 5; }
  log "STEP apply_pilot all_batches"
  docker exec -e LOG_LEVEL=ERROR -e JOB_PUBLIC_LISTING_MAX_AGE_DAYS="${MAX_AGE}" linkedin-scraper-api-pilot \
    python -m app.cli.job_lifecycle expire-public --mongo-db "$PILOT_DB" --apply --all-batches \
    >>"$LOG" 2>&1 || { log "ERROR pilot apply"; exit 6; }
fi

if [ "$APPLY_PROD" = "true" ]; then
  if [ "${JOB_EXPIRY_REQUIRE_PREVIEW_FILE:-true}" = "true" ] && [ ! -f "$PREVIEW_JSON" ]; then
    log "ERROR production apply blocked: missing preview file"
    exit 7
  fi
  log "STEP backup_production"
  bash scripts/server_mongo_backup_jobs.sh "$PROD_DB" 2>&1 | tee -a "$LOG" | grep -q BACKUP_OK \
    || { log "ERROR production backup failed"; exit 8; }
  log "STEP apply_production all_batches"
  docker exec -e LOG_LEVEL=ERROR -e JOB_PUBLIC_LISTING_MAX_AGE_DAYS="${MAX_AGE}" linkedin-scraper-api \
    python -m app.cli.job_lifecycle expire-public --mongo-db "$PROD_DB" --apply --all-batches \
    >>"$LOG" 2>&1 || { log "ERROR production apply"; exit 9; }
fi

log "DONE expiry scheduled"
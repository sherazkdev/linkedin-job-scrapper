#!/usr/bin/env bash
# Scheduled public listing expiry (posted_at / first_seen_at — not last_seen_at).
# Marks jobs EXPIRED in MongoDB; does not delete documents. Independent of collection/auth state.
set -euo pipefail
APP_DIR=/var/www/linkedin-job-scrapper
cd "$APP_DIR"
LOG_DIR=evidence/job_lifecycle
mkdir -p "$LOG_DIR"
STAMP=$(date -u +%Y%m%dT%H%M%SZ)
LOG="$LOG_DIR/expiry_scheduled_${STAMP}.log"
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

APPLY="${JOB_EXPIRY_APPLY:-false}"
MAX_AGE="${JOB_PUBLIC_LISTING_MAX_AGE_DAYS:-7}"
PILOT_DB="${PILOT_MONGO_DB_NAME:-global_jobs_pilot}"
PROD_DB="${PROMOTION_TARGET_MONGO_DB_NAME:-global_jobs}"

log "BEGIN job expiry max_age_days=${MAX_AGE} apply=${APPLY}"

_run_expiry() {
  local db="$1"
  local container="$2"
  docker exec "$container" printenv MONGO_DB_NAME | grep -qx "$db" \
    || { log "ERROR ${container} MONGO_DB_NAME != ${db}"; return 2; }
  local apply_args=()
  if [ "$APPLY" = "true" ]; then
    apply_args=(--apply)
  fi
  docker exec -e LOG_LEVEL=ERROR -e JOB_PUBLIC_LISTING_MAX_AGE_DAYS="${MAX_AGE}" "$container" \
    python -m app.cli.job_lifecycle expire-public --mongo-db "$db" "${apply_args[@]}" \
    >>"$LOG" 2>&1 || return 3
  return 0
}

log "STEP pilot_dry_run_or_apply db=${PILOT_DB}"
_run_expiry "$PILOT_DB" linkedin-scraper-api-pilot || { log "ERROR pilot expiry"; exit 4; }

log "STEP production_dry_run_or_apply db=${PROD_DB}"
_run_expiry "$PROD_DB" linkedin-scraper-api || { log "ERROR production expiry"; exit 5; }

log "DONE job expiry"
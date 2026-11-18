#!/usr/bin/env bash
# Scheduled pilot→production upsert (no auto-deprecation). Requires ALLOW_SCHEDULED_PUBLICATION_SYNC=true.
set -euo pipefail
APP_DIR=/var/www/linkedin-job-scrapper
cd "$APP_DIR"
LOG_DIR=evidence/publication_readiness
mkdir -p "$LOG_DIR" evidence/promotion_backups
STAMP=$(date -u +%Y%m%dT%H%M%SZ)
LOG="$LOG_DIR/sync_scheduled_${STAMP}.log"
RECONCILE_JSON="$LOG_DIR/reconcile_${STAMP}.json"
LOCK=/tmp/publication_sync_scheduled.lock

exec 9>"$LOCK"
if ! flock -n 9; then
  echo "[${STAMP}] SKIP overlapping sync" | tee -a "$LOG"
  exit 0
fi

log() { echo "[$(date -u +%Y-%m-%dT%H:%M:%SZ)] $*" | tee -a "$LOG"; }

if [ "${ALLOW_SCHEDULED_PUBLICATION_SYNC:-false}" != "true" ]; then
  log "SKIP ALLOW_SCHEDULED_PUBLICATION_SYNC not true"
  exit 0
fi

log "BEGIN scheduled publication sync"

docker exec linkedin-scraper-api printenv MONGO_DB_NAME | grep -qx global_jobs \
  || { log "ERROR production api db"; exit 2; }
docker exec linkedin-scraper-api-pilot printenv MONGO_DB_NAME | grep -qx global_jobs_pilot \
  || { log "ERROR pilot api db"; exit 2; }

docker exec -e LOG_LEVEL=ERROR linkedin-scraper-api-pilot \
  python -m app.cli.promote_pilot reconcile >"$RECONCILE_JSON" 2>/dev/null \
  || { log "ERROR reconcile failed"; exit 3; }

read -r VALIDATION_OK CREATE UPDATE DEPRECATE <<EOF
$(python3 -c "
import json
from pathlib import Path
raw = Path('$RECONCILE_JSON').read_text(encoding='utf-8')
start = raw.find('{')
if start < 0:
    raise SystemExit('no_json')
d=json.loads(raw[start:])
v=d.get('validation') or {}
sp=d.get('sync_plan') or {}
print(int(bool(v.get('validation_ok'))), int(sp.get('would_create_count') or 0), int(sp.get('would_update_count') or 0), int(sp.get('would_deprecate_count') or 0))
")
EOF

log "reconcile validation_ok=${VALIDATION_OK} create=${CREATE} update=${UPDATE} deprecate=${DEPRECATE} (deprecate not applied)"

if [ "$VALIDATION_OK" -ne 1 ]; then
  log "ERROR validation_failed"
  exit 4
fi
if [ "$CREATE" -eq 0 ] && [ "$UPDATE" -eq 0 ]; then
  log "DONE idle nothing to apply"
  exit 0
fi

BACKUP="evidence/promotion_backups/scheduled-${STAMP}.json"
log "STEP sync_apply backup=${BACKUP}"
docker exec \
  -e ALLOW_PILOT_TO_PRODUCTION_PROMOTION=true \
  -e LOG_LEVEL=ERROR \
  linkedin-scraper-api-pilot \
  python -m app.cli.promote_pilot sync-apply --backup "$BACKUP" \
  >>"$LOG" 2>&1 || { log "ERROR sync_apply failed"; tail -20 "$LOG"; exit 5; }

log "STEP public_api_verify"
bash scripts/server_public_api_verify_promotion.sh >>"$LOG" 2>&1 || { log "ERROR public verify failed"; exit 6; }

docker exec linkedin-scraper-api-pilot python -m app.cli.promote_pilot reconcile >>"$LOG" 2>&1 || true
log "DONE scheduled sync"
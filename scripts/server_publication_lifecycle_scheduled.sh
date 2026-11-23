#!/usr/bin/env bash
# Gated pilot→production lifecycle propagation after age-based expiry (preview + backup + lock).
# Does NOT run live LinkedIn collection. Requires explicit env gates for apply.
set -euo pipefail
APP_DIR=/var/www/linkedin-job-scrapper
cd "$APP_DIR"
LOG_DIR=evidence/publication_readiness
mkdir -p "$LOG_DIR" evidence/promotion_backups
STAMP=$(date -u +%Y%m%dT%H%M%SZ)
LOG="$LOG_DIR/lifecycle_sync_${STAMP}.json.log"
PREVIEW_JSON="$LOG_DIR/lifecycle_preview_${STAMP}.json"
LOCK=/tmp/publication_lifecycle_scheduled.lock

exec 9>"$LOCK"
if ! flock -n 9; then
  echo "[${STAMP}] SKIP overlapping lifecycle sync" | tee -a "$LOG"
  exit 0
fi

log() { echo "[$(date -u +%Y-%m-%dT%H:%M:%SZ)] $*" | tee -a "$LOG"; }

if [ "${ALLOW_SCHEDULED_LIFECYCLE_PUBLICATION:-false}" != "true" ]; then
  log "SKIP ALLOW_SCHEDULED_LIFECYCLE_PUBLICATION not true"
  exit 0
fi

log "BEGIN lifecycle publication sync"

docker exec linkedin-scraper-api-pilot \
  python -m app.cli.promote_pilot lifecycle-preview >"$PREVIEW_JSON" 2>/dev/null \
  || { log "ERROR lifecycle-preview failed"; exit 2; }

read -r WOULD_DEP WOULD_CREATE WOULD_UPDATE MASS_RISK PUB_COUNT <<EOF
$(python3 -c "
import json
from pathlib import Path
raw = Path('$PREVIEW_JSON').read_text(encoding='utf-8')
start = raw.find('{')
d=json.loads(raw[start:])
sp=d.get('sync_plan') or {}
sf=d.get('lifecycle_safety') or {}
print(
  int(sp.get('would_deprecate_count') or 0),
  int(sp.get('would_create_count') or 0),
  int(sp.get('would_update_count') or 0),
  int(sf.get('mass_deprecate_risk') or 0),
  int(sf.get('production_published_count') or 0),
)
")
EOF

log "preview dep=${WOULD_DEP} create=${WOULD_CREATE} update=${WOULD_UPDATE} published=${PUB_COUNT} mass_risk=${MASS_RISK}"

if [ "$WOULD_DEP" -eq 0 ]; then
  log "DONE nothing to propagate"
  exit 0
fi

if [ "$MASS_RISK" -eq 1 ] && [ "${ALLOW_MASS_LIFECYCLE_DEPRECATION:-false}" != "true" ]; then
  log "BLOCKED mass lifecycle deprecation (set ALLOW_MASS_LIFECYCLE_DEPRECATION=true after operator review)"
  log "PREVIEW_FILE=${PREVIEW_JSON}"
  exit 3
fi

if [ "${ALLOW_PILOT_TO_PRODUCTION_PROMOTION:-false}" != "true" ]; then
  log "SKIP apply: ALLOW_PILOT_TO_PRODUCTION_PROMOTION not true"
  exit 0
fi

BACKUP="evidence/promotion_backups/lifecycle-${STAMP}.json"
if [ "$WOULD_CREATE" -gt 0 ] || [ "$WOULD_UPDATE" -gt 0 ]; then
  log "STEP sync_apply_with_deprecate backup=${BACKUP}"
  MASS_FLAG=""
  if [ "$MASS_RISK" -eq 1 ]; then
    MASS_FLAG="--allow-mass-deprecation"
  fi
  docker exec \
    -e ALLOW_PILOT_TO_PRODUCTION_PROMOTION=true \
    -e LOG_LEVEL=ERROR \
    linkedin-scraper-api-pilot \
    python -m app.cli.promote_pilot sync-apply --deprecate ${MASS_FLAG} \
      --backup "$BACKUP" >>"$LOG" 2>&1 \
    || { log "ERROR lifecycle sync-apply failed"; tail -30 "$LOG"; exit 4; }
else
  log "STEP deprecate_stale_only"
  MASS_OK=0
  if [ "$MASS_RISK" -eq 1 ] && [ "${ALLOW_MASS_LIFECYCLE_DEPRECATION:-false}" = "true" ]; then
    MASS_OK=1
  fi
  if [ "$MASS_RISK" -eq 1 ] && [ "$MASS_OK" -ne 1 ]; then
    log "BLOCKED deprecate-stale mass risk without ALLOW_MASS_LIFECYCLE_DEPRECATION"
    exit 3
  fi
  DEP_ARGS=()
  if [ "$MASS_OK" -eq 1 ]; then
    DEP_ARGS+=(--allow-mass-deprecation)
  fi
  docker exec \
    -e ALLOW_PILOT_TO_PRODUCTION_PROMOTION=true \
    -e LOG_LEVEL=ERROR \
    linkedin-scraper-api-pilot \
    python -m app.cli.promote_pilot deprecate-stale "${DEP_ARGS[@]}" >>"$LOG" 2>&1 \
    || { log "ERROR deprecate-stale failed"; tail -30 "$LOG"; exit 4; }
fi

bash scripts/server_public_api_verify_promotion.sh >>"$LOG" 2>&1 || { log "ERROR public verify"; exit 5; }
log "DONE lifecycle publication sync"
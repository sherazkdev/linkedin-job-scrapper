#!/usr/bin/env bash
# Read-only audit + restore accidentally enabled LinkedIn pilot targets (no scheduling).
set -euo pipefail
APP_DIR=/var/www/linkedin-job-scrapper
STAMP=$(date -u +%Y%m%dT%H%M%SZ)
EVIDENCE="${APP_DIR}/evidence/target_audit/${STAMP}"
mkdir -p "${EVIDENCE}"
cd "${APP_DIR}"

MU=$(docker exec linkedin-scraper-mongodb printenv MONGO_INITDB_ROOT_USERNAME)
MP=$(docker exec linkedin-scraper-mongodb printenv MONGO_INITDB_ROOT_PASSWORD)

mongo_eval() {
  docker exec linkedin-scraper-mongodb mongosh -u "$MU" -p "$MP" \
    --authenticationDatabase admin --quiet --eval "$1"
}

log() { echo "[$(date -u +%H:%M:%SZ)] $*"; }

log "audit_before"
mongo_eval "
const dbp=db.getSiblingDB('global_jobs_pilot');
const enabled=dbp.collection_targets.find({source:'linkedin',enabled:true}).toArray();
printjson({enabled_count:enabled.length,enabled:enabled.map(t=>({country:t.country_code,keyword:t.keyword,loc:t.search_location||'',max:t.max_jobs_per_run,priority:t.priority}))});
" | tee "${EVIDENCE}/before.json"

ENABLED_CNT=$(python3 -c "import json; d=json.load(open('${EVIDENCE}/before.json')); print(d.get('enabled_count',0))")
if [ "${ENABLED_CNT}" -gt 0 ]; then
  log "backup_enabled_targets"
  cp "${EVIDENCE}/before.json" "${EVIDENCE}/enabled_backup.json"
  log "disable_all_linkedin_pilot_targets"
  mongo_eval "
const dbp=db.getSiblingDB('global_jobs_pilot');
const res=dbp.collection_targets.updateMany(
  {source:'linkedin',enabled:true},
  {\$set:{enabled:false,lock_owner:null,locked_until:null}}
);
printjson({modified:res.modifiedCount});
" | tee "${EVIDENCE}/disable.json"
else
  log "no_enabled_targets"
fi

log "audit_after"
mongo_eval "
const dbp=db.getSiblingDB('global_jobs_pilot');
printjson({enabled:dbp.collection_targets.countDocuments({source:'linkedin',enabled:true})});
" | tee "${EVIDENCE}/after.json"

BEAT=$(docker ps --format '{{.Names}}' | grep -c '^linkedin-scraper-beat$' || true)
ALLOW=$(docker exec linkedin-scraper-worker-linkedin printenv ALLOW_LIVE_LINKEDIN_COLLECTION)
log "beat=${BEAT} allow_live=${ALLOW}"
log "DONE evidence=${EVIDENCE}"
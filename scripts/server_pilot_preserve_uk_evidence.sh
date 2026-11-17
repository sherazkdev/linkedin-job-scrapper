#!/usr/bin/env bash
# Export UK pilot verification evidence from global_jobs_pilot (read-only; does not delete jobs).
set -euo pipefail
APP_DIR=/var/www/linkedin-job-scrapper
EVIDENCE_DIR="${APP_DIR}/evidence/pilot_uk_gb_software_engineer"
STAMP=$(date -u +%Y%m%dT%H%M%SZ)
mkdir -p "$EVIDENCE_DIR"

MONGO_USER=$(docker exec linkedin-scraper-mongodb printenv MONGO_INITDB_ROOT_USERNAME)
MONGO_PASS=$(docker exec linkedin-scraper-mongodb printenv MONGO_INITDB_ROOT_PASSWORD)

docker exec linkedin-scraper-mongodb mongosh -u "$MONGO_USER" -p "$MONGO_PASS" \
  --authenticationDatabase admin --quiet --eval "
const dbp = db.getSiblingDB('global_jobs_pilot');
const jobs = dbp.jobs.find({ source: 'linkedin', search_country_code: 'GB' }).sort({ last_seen_at: -1 }).toArray();
const run = dbp.collection_runs.find({ source: 'linkedin', country_code: 'GB' }).sort({ started_at: -1 }).limit(1).toArray()[0];
print(JSON.stringify({ exported_at: '${STAMP}', jobs_count: jobs.length, jobs, latest_run: run }, null, 2));
" >"${EVIDENCE_DIR}/uk_pilot_snapshot_${STAMP}.json"

echo "Wrote ${EVIDENCE_DIR}/uk_pilot_snapshot_${STAMP}.json"
wc -c "${EVIDENCE_DIR}/uk_pilot_snapshot_${STAMP}.json"
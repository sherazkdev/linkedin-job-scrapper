#!/usr/bin/env bash
# Read-only Wave 1 observation report (global_jobs_pilot).
set -euo pipefail
APP_DIR=/var/www/linkedin-job-scrapper
cd "$APP_DIR"
PILOT_DB=global_jobs_pilot
START_ISO="${WAVE1_START_ISO:-2026-11-17T06:30:30+00:00}"
MONGO_USER=$(docker exec linkedin-scraper-mongodb printenv MONGO_INITDB_ROOT_USERNAME)
MONGO_PASS=$(docker exec linkedin-scraper-mongodb printenv MONGO_INITDB_ROOT_PASSWORD)

docker exec linkedin-scraper-mongodb mongosh -u "$MONGO_USER" -p "$MONGO_PASS" \
  --authenticationDatabase admin --quiet --eval "
const pilot=db.getSiblingDB('${PILOT_DB}');
const since=new Date('${START_ISO}');
const dayAgo=new Date(Date.now()-24*3600*1000);
const verified={source:'linkedin',data_provenance:'live_api_verified',status:'active'};
const runs=pilot.collection_runs;
const jobs=pilot.jobs;
printjson({
  observation_started_at: '${START_ISO}',
  generated_at: new Date().toISOString(),
  unique_live_verified_jobs: jobs.countDocuments(verified),
  posted_within_last_24h: jobs.countDocuments({...verified,posted_at:{\$gte:dayAgo}}),
  runs_since_start: {
    completed: runs.countDocuments({source:'linkedin',dry_run:false,started_at:{\$gte:since},status:'completed'}),
    failed: runs.countDocuments({source:'linkedin',dry_run:false,started_at:{\$gte:since},status:'failed'}),
    running: runs.countDocuments({source:'linkedin',dry_run:false,status:'running'}),
    cancelled: runs.countDocuments({source:'linkedin',dry_run:false,started_at:{\$gte:since},status:'cancelled'})
  },
  countries_search_market: jobs.aggregate([
    {\$match:verified},
    {\$group:{_id:'\$search_country_code',count:{\$sum:1}}},
    {\$sort:{count:-1}}
  ]).toArray(),
  auth_class_failures: runs.countDocuments({
    source:'linkedin',dry_run:false,started_at:{\$gte:since},status:'failed',
    \$or:[
      {error_summary:/authentication/i},{error_summary:/verification/i},
      {error_summary:/session/i},{error_summary:/access_denied/i},{error_summary:/rate_limit/i}
    ]
  }),
  linkedin_enabled_targets: pilot.collection_targets.countDocuments({source:'linkedin',enabled:true}),
  daily_cap_runs_started_24h: runs.countDocuments({source:'linkedin',dry_run:false,started_at:{\$gte:dayAgo}})
});
"
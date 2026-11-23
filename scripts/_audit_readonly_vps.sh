#!/usr/bin/env bash
set -euo pipefail
cd /var/www/linkedin-job-scrapper
echo "SHA=$(git rev-parse --short HEAD)"
echo "=== containers ==="
docker ps --format '{{.Names}}' | grep -E 'linkedin-scraper|beat|worker' || true
echo "=== worker env ==="
docker exec linkedin-scraper-worker-linkedin printenv ALLOW_LIVE_LINKEDIN_COLLECTION CELERY_WORKER_MONGO_DB_NAME LINKEDIN_MAX_LIVE_RUNS_PER_24H CELERY_BEAT_DISPATCH_INTERVAL_SECONDS 2>/dev/null || true
docker exec linkedin-scraper-beat printenv CELERY_BEAT_DISPATCH_INTERVAL_SECONDS CELERY_WORKER_MONGO_DB_NAME 2>/dev/null || echo beat_off
echo "=== counts ==="
MU=$(docker exec linkedin-scraper-mongodb printenv MONGO_INITDB_ROOT_USERNAME)
MP=$(docker exec linkedin-scraper-mongodb printenv MONGO_INITDB_ROOT_PASSWORD)
docker exec linkedin-scraper-mongodb mongosh -u "$MU" -p "$MP" --authenticationDatabase admin --quiet --eval "
const v={source:'linkedin',data_provenance:'live_api_verified',status:'active'};
const pilot=db.getSiblingDB('global_jobs_pilot');
const prod=db.getSiblingDB('global_jobs');
const dayAgo=new Date(Date.now()-86400000);
printjson({
  pilot_active_verified: pilot.jobs.countDocuments(v),
  prod_active_verified: prod.jobs.countDocuments(v),
  enabled_targets: pilot.collection_targets.countDocuments({source:'linkedin',enabled:true}),
  cap_runs_24h: pilot.collection_runs.countDocuments({source:'linkedin',dry_run:false,started_at:{\$gte:dayAgo}}),
  runs_completed_24h: pilot.collection_runs.countDocuments({source:'linkedin',status:'completed',started_at:{\$gte:dayAgo}}),
  runs_failed_24h: pilot.collection_runs.countDocuments({source:'linkedin',status:'failed',started_at:{\$gte:dayAgo}}),
  auth_fails_24h: pilot.collection_runs.countDocuments({source:'linkedin',status:'failed',started_at:{\$gte:dayAgo},error_summary:/authentication|verification|session/i}),
  created_24h: pilot.collection_runs.aggregate([{\$match:{source:'linkedin',started_at:{\$gte:dayAgo}}},{\$group:{_id:null,c:{\$sum:'\$created_count'}}}]).toArray()
});
"
echo "=== keywords enabled ==="
docker exec linkedin-scraper-mongodb mongosh -u "$MU" -p "$MP" --authenticationDatabase admin --quiet --eval "
db.getSiblingDB('global_jobs_pilot').collection_targets.aggregate([
  {\$match:{source:'linkedin',enabled:true}},
  {\$group:{_id:'\$keyword',countries:{\$sum:1},max_jobs:{\$max:'\$max_jobs_per_run'}}}
]).toArray().forEach(x=>printjson(x));
"
#!/usr/bin/env bash
set -euo pipefail
PILOT_DB=global_jobs_pilot
MONGO_USER=$(docker exec linkedin-scraper-mongodb printenv MONGO_INITDB_ROOT_USERNAME)
MONGO_PASS=$(docker exec linkedin-scraper-mongodb printenv MONGO_INITDB_ROOT_PASSWORD)
REDIS_PASS=$(docker exec linkedin-scraper-redis printenv REDIS_PASSWORD)
docker exec linkedin-scraper-mongodb mongosh -u "$MONGO_USER" -p "$MONGO_PASS" --authenticationDatabase admin --quiet --eval "
const dbp=db.getSiblingDB('${PILOT_DB}');
printjson({
  run: dbp.collection_runs.find({source:'linkedin'}).sort({started_at:-1}).limit(1).toArray().map(r=>({run_id:r.run_id,status:r.status,stats:r.stats,error_summary:r.error_summary}))[0],
  jobs_count: dbp.jobs.countDocuments({source:'linkedin'}),
  enabled_targets: dbp.collection_targets.countDocuments({source:'linkedin',enabled:true}),
});
"
echo "queue_depth=$(docker exec linkedin-scraper-redis redis-cli -a "$REDIS_PASS" --no-auth-warning LLEN collection)"
docker ps --filter name=linkedin-scraper --format 'table {{.Names}}\t{{.Status}}'
curl -sf https://jobsfinder.batteryanimation2.com/health/live && echo " HTTPS_OK"
cd /var/www/linkedin-job-scrapper && git rev-parse --short HEAD
#!/usr/bin/env bash
# Read-only publication readiness: run reconciliation, job integrity, recency (no promotion apply).
set -euo pipefail
APP_DIR=/var/www/linkedin-job-scrapper
cd "$APP_DIR"
mkdir -p evidence/publication_readiness
OUT=evidence/publication_readiness/audit_$(date -u +%Y%m%dT%H%M%SZ).json
PILOT_DB=global_jobs_pilot
WAVE1_START_ISO="${WAVE1_START_ISO:-2026-11-17T06:30:30+00:00}"
MONGO_USER=$(docker exec linkedin-scraper-mongodb printenv MONGO_INITDB_ROOT_USERNAME)
MONGO_PASS=$(docker exec linkedin-scraper-mongodb printenv MONGO_INITDB_ROOT_PASSWORD)

docker exec linkedin-scraper-mongodb mongosh -u "$MONGO_USER" -p "$MONGO_PASS" \
  --authenticationDatabase admin --quiet --eval "
const pilot=db.getSiblingDB('${PILOT_DB}');
const runs=pilot.collection_runs;
const jobs=pilot.jobs;
const since=new Date('${WAVE1_START_ISO}');
const dayAgo=new Date(Date.now()-24*3600*1000);
const now=new Date();
const verified={source:'linkedin',data_provenance:'live_api_verified',status:'active'};

function statusBreakdown(match, label) {
  return runs.aggregate([
    {\$match:match},
    {\$group:{_id:'\$status',n:{\$sum:1}}},
    {\$sort:{n:-1}}
  ]).toArray();
}

const rolling24h={source:'linkedin',dry_run:false,started_at:{\$gte:dayAgo}};
const sinceWave1={source:'linkedin',dry_run:false,started_at:{\$gte:since}};
const rollingCount=runs.countDocuments(rolling24h);
const sinceCount=runs.countDocuments(sinceWave1);
const beforeWave1InWindow=runs.countDocuments({
  source:'linkedin',dry_run:false,
  started_at:{\$gte:dayAgo,\$lt:since}
});

const authOr=[
  {error_summary:/authentication/i},{error_summary:/verification/i},
  {error_summary:/session/i},{error_summary:/access_denied/i}
];
const authFails=runs.find({
  source:'linkedin',dry_run:false,started_at:{\$gte:since},status:'failed',
  \$or:authOr
},{country_code:1,error_summary:1,started_at:1,run_id:1,status:1}).toArray();

const targets=pilot.collection_targets.find({source:'linkedin'},{country_code:1,enabled:1,keyword:1}).toArray();
const enabledTargets=targets.filter(t=>t.enabled).length;
const wave1Countries=targets.map(t=>t.country_code).filter(Boolean).sort();

const countriesWithJobs=jobs.aggregate([
  {\$match:verified},
  {\$group:{_id:'\$search_country_code',count:{\$sum:1}}},
  {\$sort:{_id:1}}
]).toArray();
const countriesWithJobsSet=new Set(countriesWithJobs.map(c=>c._id));
const countriesMissingJobs=wave1Countries.filter(c=>!countriesWithJobsSet.has(c));

const allJobs=jobs.find(verified,{sourceJobId:1,search_country_code:1,posted_at:1,job_url:1,
  data_provenance:1,status:1,source:1}).toArray();
const ids=allJobs.map(j=>j.sourceJobId).filter(Boolean);
const dupIds=ids.filter((id,i)=>ids.indexOf(id)!==i);
const uniqueIds=new Set(ids);

const urlBad=allJobs.filter(j=>!j.job_url||!/\/jobs\/view\//i.test(j.job_url));
const provBad=allJobs.filter(j=>j.data_provenance!=='live_api_verified');
const statusBad=allJobs.filter(j=>j.status!=='active');
const sourceBad=allJobs.filter(j=>j.source!=='linkedin');
const missingPosted=allJobs.filter(j=>!(j.posted_at instanceof Date));

const postedLast24h=jobs.countDocuments({...verified,posted_at:{\$gte:dayAgo}});
const postedOlder=allJobs.filter(j=>j.posted_at&&j.posted_at<dayAgo).map(j=>({
  sourceJobId:j.sourceJobId,search_country_code:j.search_country_code,posted_at:j.posted_at
}));

const report={
  generated_at: now.toISOString(),
  publication_time_posted_cutoff_utc: dayAgo.toISOString(),
  wave1_observation_started_at: '${WAVE1_START_ISO}',
  run_reconciliation:{
    rolling_24h_started_total: rollingCount,
    since_wave1_start_total: sinceCount,
    since_wave1_completed: runs.countDocuments({...sinceWave1,status:'completed'}),
    since_wave1_failed: runs.countDocuments({...sinceWave1,status:'failed'}),
    before_wave1_in_rolling_24h: beforeWave1InWindow,
    rolling_24h_status_breakdown: statusBreakdown(rolling24h,'rolling'),
    since_wave1_status_breakdown: statusBreakdown(sinceWave1,'since'),
    explanation: beforeWave1InWindow>0
      ? 'rolling_24h_includes_pilot_runs_started_before_wave1_anchor'
      : 'rolling_24h_subset_of_wave1_or_no_pre_wave1_runs'
  },
  country_coverage:{
    wave1_target_count: wave1Countries.length,
    wave1_target_countries: wave1Countries,
    countries_with_verified_jobs: countriesWithJobs,
    countries_missing_jobs: countriesMissingJobs,
  },
  authentication_failures:{
    count_since_wave1: authFails.length,
    runs: authFails
  },
  job_integrity:{
    total_verified_active: allJobs.length,
    unique_source_job_ids: uniqueIds.size,
    duplicate_source_job_ids: [...new Set(dupIds)],
    invalid_job_urls: urlBad.length,
    invalid_provenance: provBad.length,
    invalid_status: statusBad.length,
    invalid_source: sourceBad.length,
    missing_posted_at: missingPosted.length,
    integrity_ok: dupIds.length===0 && urlBad.length===0 && provBad.length===0 &&
      statusBad.length===0 && sourceBad.length===0 && missingPosted.length===0 &&
      uniqueIds.size===allJobs.length
  },
  recency_at_publication:{
    posted_within_last_24h: postedLast24h,
    posted_older_than_24h_count: postedOlder.length,
    posted_older_than_24h_sample: postedOlder
  },
  enabled_linkedin_targets: enabledTargets,
  beat_running: false
};
print(JSON.stringify(report,null,2));
" | tee "$OUT"

echo "AUDIT_SAVED=$OUT"
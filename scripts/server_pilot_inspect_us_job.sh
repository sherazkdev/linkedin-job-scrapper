#!/usr/bin/env bash
set -euo pipefail
MONGO_USER=$(docker exec linkedin-scraper-mongodb printenv MONGO_INITDB_ROOT_USERNAME)
MONGO_PASS=$(docker exec linkedin-scraper-mongodb printenv MONGO_INITDB_ROOT_PASSWORD)
docker exec linkedin-scraper-mongodb mongosh -u "$MONGO_USER" -p "$MONGO_PASS" \
  --authenticationDatabase admin --quiet --eval '
const dbp = db.getSiblingDB("global_jobs_pilot");
const us = dbp.jobs.find({ source: "linkedin", search_country_code: "US" }).toArray();
const usJobCountry = dbp.jobs.find({ source: "linkedin", country_code: "US" }).toArray();
printjson({
  by_search_country_us: us.map(j => ({
    sourceJobId: j.sourceJobId,
    title: j.title,
    country_code: j.country_code,
    search_country_code: j.search_country_code,
    location_text: j.location_text,
    data_provenance: j.data_provenance,
    job_url: j.job_url,
  })),
  by_job_country_us: usJobCountry.length,
  totals: {
    PK: dbp.jobs.countDocuments({ source: "linkedin", search_country_code: "PK" }),
    GB_search: dbp.jobs.countDocuments({ source: "linkedin", search_country_code: "GB" }),
    US_search: dbp.jobs.countDocuments({ source: "linkedin", search_country_code: "US" }),
    DE_search: dbp.jobs.countDocuments({ source: "linkedin", search_country_code: "DE" }),
    AE_search: dbp.jobs.countDocuments({ source: "linkedin", search_country_code: "AE" }),
  },
});
'
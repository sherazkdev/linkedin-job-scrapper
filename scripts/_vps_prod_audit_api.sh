#!/usr/bin/env bash
set -euo pipefail
cd /var/www/linkedin-job-scrapper || exit 1
git pull --ff-only origin main 2>/dev/null || true
docker cp app/cli/production_job_audit.py linkedin-scraper-api:/tmp/production_job_audit.py
docker exec linkedin-scraper-api python /tmp/production_job_audit.py
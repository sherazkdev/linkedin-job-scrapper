#!/usr/bin/env bash
set -euo pipefail
cd /var/www/linkedin-job-scrapper || exit 1
git pull --ff-only origin main 2>/dev/null || true
docker exec linkedin-scraper-api python -m app.cli.production_job_audit 2>/dev/null || {
  docker cp app/cli/production_job_audit.py linkedin-scraper-api:/app/app/cli/production_job_audit.py
  docker exec linkedin-scraper-api python -m app.cli.production_job_audit
}
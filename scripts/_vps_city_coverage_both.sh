#!/usr/bin/env bash
set -euo pipefail
ROOT="/var/www/linkedin-job-scrapper"
docker cp "$ROOT/app/cli/city_coverage_report.py" linkedin-scraper-api:/app/app/cli/city_coverage_report.py
docker cp "$ROOT/app/cli/city_coverage_report.py" linkedin-scraper-api-pilot:/app/app/cli/city_coverage_report.py
echo "== production =="
docker exec linkedin-scraper-api python -m app.cli.city_coverage_report --database global_jobs
echo "== pilot =="
docker exec linkedin-scraper-api-pilot python -m app.cli.city_coverage_report --database global_jobs_pilot
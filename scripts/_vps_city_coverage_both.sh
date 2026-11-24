#!/usr/bin/env bash
set -euo pipefail
echo "== production =="
docker exec linkedin-scraper-api python -m app.cli.city_coverage_report --database global_jobs
echo "== pilot =="
docker exec linkedin-scraper-api-pilot python -m app.cli.city_coverage_report --database global_jobs_pilot
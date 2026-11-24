#!/usr/bin/env bash
set -euo pipefail
ROOT="/var/www/linkedin-job-scrapper"
docker cp "$ROOT/app/cli/alerts_persistence_hook_uat.py" linkedin-scraper-api-pilot:/app/app/cli/alerts_persistence_hook_uat.py
docker exec linkedin-scraper-api-pilot python -m app.cli.alerts_persistence_hook_uat
docker exec linkedin-scraper-api-pilot python -m app.cli.alerts_cleanup
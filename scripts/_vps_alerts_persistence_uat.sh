#!/usr/bin/env bash
set -euo pipefail
docker exec linkedin-scraper-api-pilot python -m app.cli.alerts_persistence_hook_uat
docker exec linkedin-scraper-api-pilot python -m app.cli.alerts_cleanup
#!/usr/bin/env bash
set -euo pipefail
docker exec linkedin-scraper-api python -m app.cli.production_job_audit
docker exec linkedin-scraper-api-pilot python -m app.cli.alerts_cleanup
echo "== prod alerts env =="
docker exec linkedin-scraper-api printenv ALERTS_API_ENABLED ALERTS_MATCHING_ENABLED 2>/dev/null || true
echo "== pilot alerts env =="
docker exec linkedin-scraper-api-pilot printenv ALERTS_API_ENABLED ALERTS_MATCHING_ENABLED MONGO_DB_NAME 2>/dev/null || true
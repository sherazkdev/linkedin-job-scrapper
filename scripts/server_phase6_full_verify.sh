#!/usr/bin/env bash
set -euo pipefail
APP_DIR=/var/www/linkedin-job-scrapper
cd "$APP_DIR"
bash scripts/server_phase6_verify_deploy.sh
bash scripts/server_verify_session.sh
docker exec linkedin-scraper-api-pilot python -m app.cli.promote_pilot validate
docker exec linkedin-scraper-api-pilot python -m app.cli.promote_pilot reconcile
docker exec linkedin-scraper-api-pilot python -m app.cli.promote_pilot monitor
docker exec linkedin-scraper-api-pilot python -m app.cli.promote_pilot deprecate-stale --dry-run
bash scripts/server_production_monitor.sh
bash scripts/server_pytest_linkedin.sh
bash scripts/server_install_readonly_monitor_cron.sh
echo "PHASE6_FULL_VERIFY_OK"
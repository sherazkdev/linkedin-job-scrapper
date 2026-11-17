#!/usr/bin/env bash
# Read-only publication + collection monitor (no Beat, no apply).
set -euo pipefail
APP_DIR=/var/www/linkedin-job-scrapper
cd "$APP_DIR"
mkdir -p evidence/publication_readiness
OUT="evidence/publication_readiness/monitor_$(date -u +%Y%m%dT%H%M%SZ).json"

docker exec linkedin-scraper-api-pilot python -m app.cli.promote_pilot monitor | tee "$OUT"
docker exec linkedin-scraper-api-pilot python -m app.cli.promote_pilot reconcile | tee "evidence/publication_readiness/reconcile_$(date -u +%Y%m%dT%H%M%SZ).json"
echo "MONITOR_SAVED=$OUT"
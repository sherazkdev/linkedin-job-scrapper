#!/usr/bin/env bash
# Install read-only monitor cron (no apply, no Beat). Idempotent.
set -euo pipefail
APP_DIR=/var/www/linkedin-job-scrapper
CRON_LINE="0 */6 * * * cd ${APP_DIR} && bash scripts/server_production_monitor.sh >>evidence/publication_readiness/monitor_cron.log 2>&1"
MARKER="# linkedin-scraper-readonly-monitor"
TMP=$(mktemp)
(crontab -l 2>/dev/null | grep -v "$MARKER" | grep -v "server_production_monitor.sh" || true) >"$TMP"
echo "$MARKER" >>"$TMP"
echo "$CRON_LINE" >>"$TMP"
crontab "$TMP"
rm -f "$TMP"
echo "CRON_INSTALLED"
crontab -l | grep -F server_production_monitor || true
#!/usr/bin/env bash
# Install 24/7 Wave 1 observer watchdog + scheduled publication sync (idempotent).
set -euo pipefail
APP_DIR=/var/www/linkedin-job-scrapper
OBS_LINE="*/10 * * * * cd ${APP_DIR} && bash scripts/server_wave1_observer_check.sh >>evidence/wave1_observation/observer_cron.log 2>&1 # linkedin-wave1-observer-watch"
SYNC_LINE="30 */6 * * * cd ${APP_DIR} && ALLOW_SCHEDULED_PUBLICATION_SYNC=true bash scripts/server_publication_sync_scheduled.sh >>evidence/publication_readiness/sync_cron.log 2>&1 # linkedin-publication-sync"
MONITOR_LINE="0 */6 * * * cd ${APP_DIR} && bash scripts/server_production_monitor.sh >>evidence/publication_readiness/monitor_cron.log 2>&1 # linkedin-scraper-readonly-monitor"
EXPIRY_LINE="15 3 * * * cd ${APP_DIR} && ALLOW_SCHEDULED_JOB_EXPIRY=true JOB_EXPIRY_APPLY_PILOT=true bash scripts/server_job_expiry_scheduled.sh >>evidence/job_lifecycle/expiry_cron.log 2>&1 # linkedin-job-expiry"
LIFECYCLE_LINE="45 3 * * 0 cd ${APP_DIR} && ALLOW_SCHEDULED_LIFECYCLE_PUBLICATION=true bash scripts/server_publication_lifecycle_scheduled.sh >>evidence/publication_readiness/lifecycle_cron.log 2>&1 # linkedin-lifecycle-sync"
TMP=$(mktemp)
{
  echo "CRON_TZ=UTC"
  crontab -l 2>/dev/null \
  | grep -v '^CRON_TZ=' \
  | grep -v 'linkedin-wave1-observer-watch' \
  | grep -v 'linkedin-publication-sync' \
  | grep -v 'linkedin-scraper-readonly-monitor' \
  | grep -v 'server_wave1_observer_check.sh' \
  | grep -v 'server_publication_sync_scheduled.sh' \
  | grep -v 'server_production_monitor.sh' \
  | grep -v 'server_job_expiry_scheduled.sh' \
  | grep -v 'server_publication_lifecycle_scheduled.sh' \
  | grep -v 'linkedin-job-expiry' \
  | grep -v 'linkedin-lifecycle-sync' \
  || true
} >"$TMP"
echo "$OBS_LINE" >>"$TMP"
echo "$SYNC_LINE" >>"$TMP"
echo "$MONITOR_LINE" >>"$TMP"
echo "$EXPIRY_LINE" >>"$TMP"
echo "$LIFECYCLE_LINE" >>"$TMP"
crontab "$TMP"
rm -f "$TMP"
echo "CRON_INSTALLED"
echo "CRON_TZ=UTC (all schedules below are UTC — verify with: timedatectl)"
crontab -l | grep -E 'CRON_TZ|linkedin-wave1|linkedin-publication|linkedin-scraper-readonly|linkedin-job-expiry|linkedin-lifecycle' || true
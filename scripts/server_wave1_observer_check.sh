#!/usr/bin/env bash
# Ensure continuous Wave 1 observer is running (restart if exited).
set -euo pipefail
APP_DIR=/var/www/linkedin-job-scrapper
cd "$APP_DIR"
LOG=evidence/wave1_observation/observer.log
mkdir -p evidence/wave1_observation

if ! docker ps --format '{{.Names}}' | grep -qx linkedin-scraper-beat; then
  echo "SKIP observer_check beat_off"
  exit 0
fi

if pgrep -f 'bash scripts/server_wave1_observer.sh' >/dev/null 2>&1; then
  echo "OBSERVER_RUNNING pid=$(pgrep -f 'bash scripts/server_wave1_observer.sh' | head -1)"
else
  echo "START observer"
  nohup bash scripts/server_wave1_observer.sh >>"$LOG" 2>&1 &
  echo "OBSERVER_PID=$!"
fi
echo "OBSERVER_CHECK_OK mode=continuous"
tail -3 "$LOG" 2>/dev/null || true
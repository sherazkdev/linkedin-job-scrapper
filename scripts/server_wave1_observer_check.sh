#!/usr/bin/env bash
set -euo pipefail
APP_DIR=/var/www/linkedin-job-scrapper
cd "$APP_DIR"
START_FILE=evidence/wave1_observation/wave1_started_at.json
LOG=evidence/wave1_observation/observer.log

if ! python3 -c "import json; json.load(open('$START_FILE'))" 2>/dev/null; then
  echo "FIX invalid_start_json"
  printf '%s\n' '{"started_at":"2026-11-17T06:30:30+00:00"}' >"$START_FILE"
fi

if ! pgrep -f server_wave1_observer.sh >/dev/null 2>&1; then
  echo "START observer"
  nohup bash scripts/server_wave1_observer.sh >>"$LOG" 2>&1 &
else
  echo "OBSERVER_PID=$(pgrep -f server_wave1_observer.sh | head -1)"
fi

python3 - <<'PY'
import json
from datetime import datetime, timezone
from pathlib import Path
p = Path("evidence/wave1_observation/wave1_started_at.json")
d = json.loads(p.read_text())
t = datetime.fromisoformat(d["started_at"].replace("Z", "+00:00"))
end = t.timestamp() + 86400
now = datetime.now(timezone.utc).timestamp()
print("started_at", d["started_at"])
print("ends_at_utc", datetime.fromtimestamp(end, tz=timezone.utc).isoformat())
print("seconds_remaining", max(0, int(end - now)))
print("window_complete", now >= end)
PY

tail -5 "$LOG" 2>/dev/null || true
echo "OBSERVER_CHECK_OK"
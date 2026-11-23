#!/usr/bin/env bash
# Wave 1 activation — pilot DB only, Beat + live worker-linkedin, 24h observer.
set -euo pipefail
APP_DIR=/var/www/linkedin-job-scrapper
cd "$APP_DIR"
# shellcheck source=lib_compose.sh
. scripts/lib_compose.sh
export GIT_TERMINAL_PROMPT=0
WAVE1_CONTAINER=linkedin-scraper-worker-linkedin
WAVE1_FAILED=0
OBSERVER_PID=""

wave1_activation_cleanup() {
  if [ "$WAVE1_FAILED" -eq 1 ]; then
    bash scripts/server_wave1_stop.sh activation_failed
  fi
}
trap wave1_activation_cleanup EXIT

wave1_fail() {
  WAVE1_FAILED=1
  exit "${1:-1}"
}

git pull --ff-only origin main
echo "DEPLOYED_SHA=$(git rev-parse HEAD)"

bash scripts/server_wave1_preflight.sh

"${COMPOSE[@]}" build worker-linkedin

echo "STEP stop_generic_worker"
docker stop linkedin-scraper-worker 2>/dev/null || true
docker rm -f linkedin-scraper-worker 2>/dev/null || true

echo "STEP enable_wave1_targets"
WAVE1_ENABLE_GROUP="${WAVE1_ENABLE_GROUP:-software_core}"
WAVE1_MAX_JOBS_PER_RUN="${WAVE1_MAX_JOBS_PER_RUN:-}"
ENABLE_CMD=(python -m app.cli.wave1_ops enable-group --group "${WAVE1_ENABLE_GROUP}")
if [ -n "${WAVE1_MAX_JOBS_PER_RUN}" ]; then
  ENABLE_CMD+=(--max-jobs "${WAVE1_MAX_JOBS_PER_RUN}")
fi
"${COMPOSE[@]}" run --rm --no-deps worker-linkedin "${ENABLE_CMD[@]}"
START_ISO=$(date -u +%Y-%m-%dT%H:%M:%S+00:00)
mkdir -p evidence/wave1_observation
printf '%s\n' "{\"started_at\":\"${START_ISO}\"}" >evidence/wave1_observation/wave1_started_at.json
python3 -c "
import json, os
from pathlib import Path
Path('evidence/wave1_observation').mkdir(parents=True, exist_ok=True)
act = Path('evidence/wave1_observation/wave1_activation.json')
if act.is_file():
    data = json.loads(act.read_text(encoding='utf-8'))
else:
    data = {}
data.update({
    'activated_at': '${START_ISO}',
    'group': os.environ.get('WAVE1_ENABLE_GROUP', 'software_core'),
    'max_jobs_per_run_override': os.environ.get('WAVE1_MAX_JOBS_PER_RUN') or None,
})
act.write_text(json.dumps(data, indent=2), encoding='utf-8')
"
echo "WAVE1_TARGETS group=${WAVE1_ENABLE_GROUP} max_jobs=${WAVE1_MAX_JOBS_PER_RUN:-<group_default>}"
if [ -f evidence/wave1_observation/wave1_activation.json ]; then
  cat evidence/wave1_observation/wave1_activation.json
fi

echo "STEP start_worker_only"
"${COMPOSE[@]}" --profile celery-linkedin up -d --force-recreate worker-linkedin
docker stop linkedin-scraper-worker 2>/dev/null || true
docker rm -f linkedin-scraper-worker 2>/dev/null || true

echo "STEP wait_worker_ready"
READY=0
for i in $(seq 1 40); do
  if docker exec "$WAVE1_CONTAINER" python -m app.cli.celery_ops worker-ready --timeout 8; then
    READY=1
    echo "WORKER_READY poll=$i"
    break
  fi
  if docker logs --tail 40 "$WAVE1_CONTAINER" 2>&1 | grep -qE 'linkedin-worker@[^ ]+ ready\.'; then
    if docker exec "$WAVE1_CONTAINER" python -m app.cli.celery_ops worker-ready --timeout 12; then
      READY=1
      echo "WORKER_READY poll=$i log_marker=ready"
      break
    fi
  fi
  sleep 3
done
[ "$READY" -eq 1 ] || wave1_fail 10

docker exec "$WAVE1_CONTAINER" printenv CELERY_WORKER_MONGO_DB_NAME | grep -qx global_jobs_pilot \
  || wave1_fail 11
docker exec "$WAVE1_CONTAINER" printenv ALLOW_LIVE_LINKEDIN_COLLECTION | grep -qx true \
  || wave1_fail 12

echo "STEP start_observer"
chmod +x scripts/server_wave1_observer.sh scripts/server_wave1_stop.sh
mkdir -p evidence/wave1_observation
nohup bash scripts/server_wave1_observer.sh >evidence/wave1_observation/observer.log 2>&1 &
OBSERVER_PID=$!
echo "OBSERVER_PID=${OBSERVER_PID}"
sleep 2
kill -0 "$OBSERVER_PID" 2>/dev/null || wave1_fail 13

echo "STEP start_beat"
"${COMPOSE[@]}" --profile celery --profile celery-linkedin up -d --no-deps beat
sleep 5
docker ps --format '{{.Names}}' | grep -qx linkedin-scraper-beat || wave1_fail 14
docker exec linkedin-scraper-beat printenv CELERY_WORKER_MONGO_DB_NAME | grep -qx global_jobs_pilot \
  || wave1_fail 15

trap - EXIT
WAVE1_FAILED=0
echo "WAVE1_ACTIVATED"
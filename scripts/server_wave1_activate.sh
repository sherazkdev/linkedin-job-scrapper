#!/usr/bin/env bash
# Wave 1 activation — pilot DB only, Beat + live worker-linkedin, 24h observer.
set -euo pipefail
APP_DIR=/var/www/linkedin-job-scrapper
cd "$APP_DIR"
COMPOSE="docker compose -f compose.yaml -f compose.contabo-vps.yaml -f compose.contabo-wave1.yaml -p linkedin-scraper"
export GIT_TERMINAL_PROMPT=0

git pull --ff-only origin main
echo "DEPLOYED_SHA=$(git rev-parse HEAD)"

bash scripts/server_wave1_preflight.sh

$COMPOSE build worker-linkedin

echo "STEP stop_generic_worker"
docker stop linkedin-scraper-worker 2>/dev/null || true
docker rm -f linkedin-scraper-worker 2>/dev/null || true

echo "STEP enable_wave1_targets"
$COMPOSE run --rm --no-deps worker-linkedin python -m app.cli.wave1_ops enable
START_ISO=$(date -u +%Y-%m-%dT%H:%M:%S+00:00)
mkdir -p evidence/wave1_observation
printf '%s\n' "{\"started_at\":\"${START_ISO}\"}" >evidence/wave1_observation/wave1_started_at.json

echo "STEP start_worker_beat"
$COMPOSE --profile celery-linkedin up -d --force-recreate worker-linkedin
$COMPOSE --profile celery --profile celery-linkedin up -d --no-deps beat
docker stop linkedin-scraper-worker 2>/dev/null || true
docker rm -f linkedin-scraper-worker 2>/dev/null || true

sleep 8
docker exec linkedin-scraper-worker-linkedin python -m app.cli.celery_ops ping
docker exec linkedin-scraper-beat printenv CELERY_WORKER_MONGO_DB_NAME | grep -qx global_jobs_pilot
docker exec linkedin-scraper-worker-linkedin printenv ALLOW_LIVE_LINKEDIN_COLLECTION | grep -qx true

echo "STEP start_observer"
chmod +x scripts/server_wave1_observer.sh scripts/server_wave1_stop.sh
mkdir -p evidence/wave1_observation
nohup bash scripts/server_wave1_observer.sh >evidence/wave1_observation/observer.log 2>&1 &
echo "OBSERVER_PID=$!"
echo "WAVE1_ACTIVATED"
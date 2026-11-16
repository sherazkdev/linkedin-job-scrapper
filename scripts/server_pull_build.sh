#!/usr/bin/env bash
set -euo pipefail
APP_DIR=/var/www/linkedin-job-scrapper
cd "$APP_DIR"
COMPOSE="docker compose -f compose.yaml -f compose.contabo-vps.yaml -p linkedin-scraper"
git fetch origin main
git pull --ff-only origin main
echo "DEPLOYED_SHA=$(git rev-parse HEAD)"
echo "DEPLOYED_SHORT=$(git rev-parse --short HEAD)"
$COMPOSE build worker-linkedin
$COMPOSE --profile celery-linkedin up -d --force-recreate worker-linkedin
docker exec linkedin-scraper-worker-linkedin python -m app.cli.linkedin_session status
docker exec linkedin-scraper-worker-linkedin python -c "from app.core.config import get_settings; s=get_settings(); print({'live':s.allow_live_linkedin_collection,'celery_li':s.celery_allow_linkedin_tasks,'worker_db':s.celery_worker_mongo_db_name})"
BEAT_COUNT=$(docker ps --filter name=linkedin-scraper-beat --format '{{.Names}}' | wc -l)
echo "beat_containers=$BEAT_COUNT"
curl -sf https://jobsfinder.batteryanimation2.com/health/live && echo " HTTPS_OK"
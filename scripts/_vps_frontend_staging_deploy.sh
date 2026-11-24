#!/usr/bin/env bash
set -euo pipefail
cd /var/www/linkedin-job-scrapper || exit 1
git pull --ff-only origin main
SHA="$(git rev-parse HEAD)"
export FRONTEND_STAGING_GIT_SHA="${FRONTEND_STAGING_GIT_SHA:-$SHA}"
export FRONTEND_STAGING_PORT="${FRONTEND_STAGING_PORT:-13010}"
export FRONTEND_STAGING_APP_URL="${FRONTEND_STAGING_APP_URL:-http://127.0.0.1:${FRONTEND_STAGING_PORT}}"

COMPOSE=(docker compose -f compose.yaml -f compose.contabo-vps.yaml \
  -f compose.contabo-pilot-api.yaml -f compose.contabo-alerts-flags.yaml \
  -f compose.contabo-frontend-staging.yaml -p linkedin-scraper)

if docker image inspect "linkedin-scraper-frontend-staging:${FRONTEND_STAGING_GIT_SHA}" >/dev/null 2>&1; then
  echo "image_already_built sha=${FRONTEND_STAGING_GIT_SHA}"
else
  if docker image inspect linkedin-scraper-frontend-staging:latest >/dev/null 2>&1; then
    PREV="$(docker inspect linkedin-scraper-frontend-staging:latest --format '{{index .Config.Labels "org.opencontainers.image.revision"}}' 2>/dev/null || echo unknown)"
    docker tag linkedin-scraper-frontend-staging:latest "linkedin-scraper-frontend-staging:rollback-${PREV}"
    echo "tagged_rollback_image=linkedin-scraper-frontend-staging:rollback-${PREV}"
  fi
  echo "building_frontend sha=${FRONTEND_STAGING_GIT_SHA}"
  if [ "${FRONTEND_FORCE_REBUILD:-0}" = "1" ]; then
    "${COMPOSE[@]}" build --no-cache frontend-staging
  else
    "${COMPOSE[@]}" build frontend-staging
  fi
  docker tag "linkedin-scraper-frontend-staging:${FRONTEND_STAGING_GIT_SHA}" linkedin-scraper-frontend-staging:latest
fi

"${COMPOSE[@]}" up -d --no-deps frontend-staging

sleep 5
RUN_SHA="$(docker exec linkedin-scraper-frontend-staging node -e "fetch('http://127.0.0.1:3000/api/health').then(r=>r.json()).then(j=>console.log(j.git_sha)).catch(()=>process.exit(1))")"
if [ "$RUN_SHA" != "$FRONTEND_STAGING_GIT_SHA" ]; then
  echo "SHA_MISMATCH expected=${FRONTEND_STAGING_GIT_SHA} running=${RUN_SHA}" >&2
  exit 1
fi
docker exec linkedin-scraper-frontend-staging node -e "fetch('http://127.0.0.1:3000/').then(r=>{if(!r.ok)process.exit(1)}).catch(()=>process.exit(1))"
echo "frontend_staging_ok port=${FRONTEND_STAGING_PORT} sha=${RUN_SHA} loopback_only"
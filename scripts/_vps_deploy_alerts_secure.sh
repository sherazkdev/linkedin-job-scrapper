#!/usr/bin/env bash
# Deploy alerts hardening commit — api + api-pilot only; preserve dirty files; no Beat/worker unless needed.
set -euo pipefail
REPO=/var/www/linkedin-job-scrapper
TARGET_SHA="${1:-}"
cd "$REPO"
STASH_LABEL="pre-deploy-alerts-$(date -u +%Y%m%dT%H%M%SZ)"
git stash push -u -m "$STASH_LABEL" || true
git fetch origin main
if [[ -n "$TARGET_SHA" ]]; then
  git checkout "$TARGET_SHA"
else
  git pull --ff-only origin main
fi
HEAD_SHA=$(git rev-parse HEAD)
echo "DEPLOY_SHA=$HEAD_SHA"
COMPOSE=(docker compose -f compose.yaml -f compose.contabo-vps.yaml -f compose.contabo-alerts-flags.yaml -f compose.contabo-pilot-api.yaml -p linkedin-scraper)
"${COMPOSE[@]}" build api api-pilot
"${COMPOSE[@]}" up -d --no-deps api api-pilot
sleep 6
docker exec linkedin-scraper-api printenv ALERTS_API_ENABLED
docker exec linkedin-scraper-api-pilot printenv ALERTS_API_ENABLED MONGO_DB_NAME
docker exec linkedin-scraper-api python -c "
import asyncio
from app.core.config import get_settings
from app.database.temp_database import open_database
async def main():
    s=get_settings()
    async with open_database('global_jobs') as db:
        prod=await db.jobs.count_documents({})
    async with open_database('global_jobs_pilot') as db:
        pilot=await db.jobs.count_documents({})
    print({'production': prod, 'pilot': pilot})
asyncio.run(main())
"
docker exec linkedin-scraper-api python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health/live')"
docker exec linkedin-scraper-api-pilot python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health/live')"
git stash list | head -3 || true
echo "DEPLOY_DONE $HEAD_SHA"
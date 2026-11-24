#!/usr/bin/env bash
set -euo pipefail
cd /var/www/linkedin-job-scrapper || exit 1
SHA="$(git rev-parse HEAD)"
RUN_SHA="$(docker exec linkedin-scraper-frontend-staging node -e "fetch('http://127.0.0.1:3000/api/health').then(r=>r.json()).then(j=>console.log(j.git_sha)).catch(()=>process.exit(1))")"
echo "expected_sha=$SHA"
echo "running_sha=$RUN_SHA"
docker inspect linkedin-scraper-frontend-staging --format 'image={{.Config.Image}} revision={{index .Config.Labels "org.opencontainers.image.revision"}}'
test "$RUN_SHA" = "$SHA"
echo "staging_health_ok"
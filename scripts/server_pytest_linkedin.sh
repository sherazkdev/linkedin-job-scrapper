#!/usr/bin/env bash
# LinkedIn regression + Mongo integration tests on VPS (api image for DB; collector for Playwright).
set -euo pipefail
APP_DIR=/var/www/linkedin-job-scrapper
cd "$APP_DIR"
COMPOSE="docker compose -f compose.yaml -f compose.contabo-vps.yaml -p linkedin-scraper"
COLLECTOR_IMAGE="${LINKEDIN_WORKER_IMAGE:-global-jobs-collector-worker:latest}"
NET="${DOCKER_NETWORK:-linkedin_scraper_internal}"

MONGO_USER=$(docker exec linkedin-scraper-mongodb printenv MONGO_INITDB_ROOT_USERNAME)
MONGO_PASS=$(docker exec linkedin-scraper-mongodb printenv MONGO_INITDB_ROOT_PASSWORD)
REDIS_PASS=$(docker exec linkedin-scraper-redis printenv REDIS_PASSWORD 2>/dev/null || true)
MONGO_URI="mongodb://${MONGO_USER}:${MONGO_PASS}@mongodb:27017/?authSource=admin"
if [ -n "$REDIS_PASS" ]; then
  REDIS_URL="redis://:${REDIS_PASS}@redis:6379/0"
else
  REDIS_URL="redis://redis:6379/0"
fi

PYTEST_COMMON=(
  tests/collection/test_linkedin_pagination.py
  tests/collection/test_linkedin_parser.py::test_dedupe_and_cap_search_cards
  tests/collection/test_collection_error_handler.py
  tests/collection/test_linkedin_timing.py::test_linkedin_adapter_timeout_estimate_exceeds_default_collection_timeout
  tests/collection/test_linkedin_adapter_metrics.py
  tests/collection/test_linkedin_adapter_offline.py
)

echo "=== linkedin pytest (api / Mongo integration) ==="
$COMPOSE run --rm --no-deps \
  -v "$APP_DIR/tests:/app/tests:ro" \
  -v "$APP_DIR/tests/fixtures:/app/tests/fixtures:ro" \
  -e MONGO_URI="$MONGO_URI" \
  -e REDIS_URL="$REDIS_URL" \
  -e MONGO_DB_NAME=global_jobs_test \
  -e RUN_INTEGRATION=1 \
  -e ALLOW_LIVE_LINKEDIN_COLLECTION=false \
  api \
  python -m pytest "${PYTEST_COMMON[@]}" \
    tests/collection/test_linkedin_offline_persistence_api.py \
    -q --tb=short

echo "=== linkedin pytest (collector / Playwright detail-skip) ==="
docker run --rm \
  --network "$NET" \
  -v "$APP_DIR/tests:/app/tests:ro" \
  -e MONGO_URI="$MONGO_URI" \
  -e REDIS_URL="$REDIS_URL" \
  -e MONGO_DB_NAME=global_jobs_test \
  -e ALLOW_LIVE_LINKEDIN_COLLECTION=true \
  "$COLLECTOR_IMAGE" \
  python -m pytest \
    tests/collection/test_linkedin_detail_skip.py \
    -q --tb=short

echo "PYTEST_LINKEDIN_OK"
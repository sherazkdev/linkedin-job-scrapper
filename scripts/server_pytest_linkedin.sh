#!/usr/bin/env bash
# Run LinkedIn offline regression tests inside worker image (mount repo tests).
set -euo pipefail
APP_DIR=/var/www/linkedin-job-scrapper
cd "$APP_DIR"
IMAGE="${LINKEDIN_WORKER_IMAGE:-global-jobs-collector-worker:latest}"
NET="${DOCKER_NETWORK:-linkedin_scraper_internal}"
MONGO_USER=$(docker exec linkedin-scraper-mongodb printenv MONGO_INITDB_ROOT_USERNAME)
MONGO_PASS=$(docker exec linkedin-scraper-mongodb printenv MONGO_INITDB_ROOT_PASSWORD)
REDIS_PASS=$(docker exec linkedin-scraper-redis printenv REDIS_PASSWORD 2>/dev/null || true)
export MONGO_URI="mongodb://${MONGO_USER}:${MONGO_PASS}@mongodb:27017/?authSource=admin"
if [ -n "$REDIS_PASS" ]; then
  export REDIS_URL="redis://:${REDIS_PASS}@redis:6379/0"
else
  export REDIS_URL="${REDIS_URL:-redis://redis:6379/0}"
fi
export MONGO_DB_NAME="${MONGO_DB_NAME:-global_jobs_test}"

docker run --rm \
  --network "$NET" \
  -v "$APP_DIR/tests:/app/tests:ro" \
  -e MONGO_URI \
  -e REDIS_URL \
  -e MONGO_DB_NAME \
  -e ALLOW_LIVE_LINKEDIN_COLLECTION=false \
  -e RUN_INTEGRATION=1 \
  -v "$APP_DIR/tests/fixtures:/app/tests/fixtures:ro" \
  "$IMAGE" \
  python -m pytest \
    tests/collection/test_linkedin_pagination.py \
    tests/collection/test_linkedin_parser.py::test_dedupe_and_cap_search_cards \
    tests/collection/test_linkedin_detail_skip.py \
    tests/collection/test_collection_error_handler.py \
    tests/collection/test_linkedin_timing.py::test_linkedin_adapter_timeout_estimate_exceeds_default_collection_timeout \
    tests/collection/test_linkedin_offline_persistence_api.py \
    -q --tb=short
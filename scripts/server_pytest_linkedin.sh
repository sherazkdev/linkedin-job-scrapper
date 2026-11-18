#!/usr/bin/env bash
# Full LinkedIn regression + Mongo integration (collector image: Playwright + app + pytest).
set -euo pipefail
APP_DIR=/var/www/linkedin-job-scrapper
cd "$APP_DIR"
COLLECTOR_IMAGE="${LINKEDIN_WORKER_IMAGE:-global-jobs-collector-worker:latest}"
NET="${DOCKER_NETWORK:-linkedin_scraper_internal}"

MONGO_USER=$(docker exec linkedin-scraper-mongodb printenv MONGO_INITDB_ROOT_USERNAME)
MONGO_PASS=$(docker exec linkedin-scraper-mongodb printenv MONGO_INITDB_ROOT_PASSWORD)
REDIS_PASS="$(docker exec linkedin-scraper-redis printenv REDIS_PASSWORD 2>/dev/null || true)"
if [ -z "$REDIS_PASS" ] && [ -f "$APP_DIR/.env" ]; then
  REDIS_PASS="$(grep -E '^REDIS_PASSWORD=' "$APP_DIR/.env" | cut -d= -f2- | tr -d '\r\"' || true)"
fi
MONGO_URI="mongodb://${MONGO_USER}:${MONGO_PASS}@mongodb:27017/?authSource=admin"
if [ -n "$REDIS_PASS" ]; then
  REDIS_URL="redis://:${REDIS_PASS}@redis:6379/0"
else
  REDIS_URL="redis://redis:6379/0"
fi

docker run --rm \
  --network "$NET" \
  -v "$APP_DIR/app:/app/app:ro" \
  -v "$APP_DIR/tests:/app/tests:ro" \
  -v "$APP_DIR/tests/fixtures:/app/tests/fixtures:ro" \
  -v "$APP_DIR/config:/app/config:ro" \
  -e MONGO_URI="$MONGO_URI" \
  -e REDIS_URL="$REDIS_URL" \
  -e MONGO_DB_NAME=global_jobs_test \
  -e RUN_INTEGRATION=1 \
  -e ALLOW_LIVE_LINKEDIN_COLLECTION=false \
  "$COLLECTOR_IMAGE" \
  python -m pytest \
    tests/collection/test_linkedin_pagination.py \
    tests/collection/test_linkedin_pagination_exhausted.py \
    tests/collection/test_linkedin_parser.py \
    tests/collection/test_linkedin_detail_skip.py \
    tests/collection/test_collection_error_handler.py \
    tests/collection/test_linkedin_timing.py \
    tests/collection/test_linkedin_adapter_metrics.py \
    tests/collection/test_linkedin_adapter_offline.py \
    tests/collection/test_linkedin_offline_persistence_api.py \
    tests/api/test_job_filters.py \
    tests/api/test_country_vs_search_country_filter.py \
    tests/workers/test_fair_dispatch.py \
    tests/workers/test_target_eligibility.py \
    tests/workers/test_worker_readiness.py \
    tests/cli/test_celery_ops_worker_ready.py \
    tests/scripts/test_wave1_activate_script.py \
    tests/scripts/test_production_ops_scripts.py \
    tests/collection/test_target_last_run_stats.py \
    tests/scheduling/test_rollout_plan.py \
    tests/scheduling/test_linkedin_daily_cap.py \
    tests/scripts/test_pilot_smoke_pilot_api.py \
    tests/promotion/test_pilot_to_production.py \
    tests/promotion/test_publication_sync_pipeline.py \
    tests/promotion/test_deprecation_safety.py \
    tests/api/test_jobs_list_contract.py \
    -q --tb=short

echo "PYTEST_LINKEDIN_OK"
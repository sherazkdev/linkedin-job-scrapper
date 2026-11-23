import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.core.config import Settings, get_settings
from app.core.logging import configure_logging
from app.database.alert_indexes import ensure_alert_indexes
from app.database.collection_indexes import ensure_collection_indexes
from app.database.indexes import ensure_job_indexes
from app.database.mongodb import get_mongodb
from app.database.redis_client import get_redis_client

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    settings: Settings = get_settings()
    configure_logging(settings)
    logger.info("Starting application env=%s", settings.app_env)
    if settings.is_production:
        if not settings.api_cors_origins.strip():
            logger.warning(
                "APP_ENV=production but API_CORS_ORIGINS is empty (browser clients blocked)"
            )
        if not settings.internal_ops_token:
            logger.warning(
                "APP_ENV=production but INTERNAL_OPS_TOKEN unset (internal routes return 404)"
            )

    mongodb = get_mongodb()
    redis_client = get_redis_client()

    await mongodb.connect()
    await redis_client.connect()
    await ensure_job_indexes(mongodb.database)
    await ensure_collection_indexes(
        mongodb.database,
        migrate_target_search_location=settings.allow_collection_target_index_migration,
    )
    if settings.alerts_api_enabled:
        await ensure_alert_indexes(mongodb.database)

    app.state.mongodb = mongodb
    app.state.redis = redis_client
    app.state.settings = settings

    try:
        yield
    finally:
        logger.info("Shutting down application")
        await redis_client.disconnect()
        await mongodb.disconnect()

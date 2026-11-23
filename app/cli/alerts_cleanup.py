"""Remove integration-tagged alert test data from pilot Mongo (never touches jobs)."""

from __future__ import annotations

import asyncio
import logging

from app.core.config import get_settings
from app.database.temp_database import open_database
from app.modules.alerts.constants import (
    ALERT_DIGEST_DELIVERIES,
    ALERT_DIGEST_STATE,
    ALERT_NOTIFICATIONS,
    ALERT_SUBSCRIBERS,
    SAVED_JOB_SEARCHES,
    TEST_SUBSCRIBER_TAG,
)

logger = logging.getLogger(__name__)


async def _purge_integration() -> dict[str, int]:
    settings = get_settings()
    async with open_database(settings.mongo_db_name) as database:
        subs_col = database[ALERT_SUBSCRIBERS]
        ids = [
            str(doc["subscriber_id"])
            async for doc in subs_col.find({"purpose": TEST_SUBSCRIBER_TAG}, {"subscriber_id": 1})
        ]
        if not ids:
            return {"subscribers": 0}
        searches = await database[SAVED_JOB_SEARCHES].delete_many(
            {"subscriber_id": {"$in": ids}}
        )
        notifs = await database[ALERT_NOTIFICATIONS].delete_many({"subscriber_id": {"$in": ids}})
        digest = await database[ALERT_DIGEST_STATE].delete_many({"subscriber_id": {"$in": ids}})
        deliveries = await database[ALERT_DIGEST_DELIVERIES].delete_many(
            {"subscriber_id": {"$in": ids}}
        )
        subs = await subs_col.delete_many({"purpose": TEST_SUBSCRIBER_TAG})
        return {
            "subscribers": subs.deleted_count,
            "searches": searches.deleted_count,
            "notifications": notifs.deleted_count,
            "digest_state": digest.deleted_count,
            "digest_deliveries": deliveries.deleted_count,
        }


def main() -> None:
    logging.basicConfig(level=logging.INFO)
    stats = asyncio.run(_purge_integration())
    logger.info("integration cleanup complete stats=%s", stats)


if __name__ == "__main__":
    main()
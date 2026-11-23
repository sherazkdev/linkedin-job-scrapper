import logging
from typing import Any

from pymongo.asynchronous.database import AsyncDatabase

from app.modules.alerts.constants import (
    ALERT_DIGEST_STATE,
    ALERT_NOTIFICATIONS,
    ALERT_SUBSCRIBERS,
    SAVED_JOB_SEARCHES,
)

logger = logging.getLogger(__name__)


async def ensure_alert_indexes(database: AsyncDatabase[Any]) -> None:
    subs = database[ALERT_SUBSCRIBERS]
    await subs.create_index([("subscriber_id", 1)], unique=True, name="uniq_alert_subscriber_id")
    await subs.create_index([("token_hash", 1)], unique=True, name="uniq_alert_token_hash")

    searches = database[SAVED_JOB_SEARCHES]
    await searches.create_index([("subscriber_id", 1), ("created_at", -1)], name="idx_search_subscriber")
    await searches.create_index(
        [("subscriber_id", 1), ("enabled", 1)],
        name="idx_search_subscriber_enabled",
    )

    notifs = database[ALERT_NOTIFICATIONS]
    await notifs.create_index(
        [("subscriber_id", 1), ("created_at", -1)],
        name="idx_notif_subscriber_created",
    )
    await notifs.create_index(
        [("subscriber_id", 1), ("read_at", 1)],
        name="idx_notif_subscriber_read",
    )
    await notifs.create_index(
        [("subscriber_id", 1), ("event_key", 1), ("job_id", 1)],
        unique=True,
        name="uniq_notif_subscriber_event_job",
    )

    digest = database[ALERT_DIGEST_STATE]
    await digest.create_index([("subscriber_id", 1)], unique=True, name="uniq_digest_subscriber")
    logger.info("MongoDB alert indexes ensured")
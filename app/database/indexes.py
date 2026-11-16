import logging
from typing import Any

from pymongo.asynchronous.database import AsyncDatabase

logger = logging.getLogger(__name__)

JOBS_COLLECTION = "jobs"


async def ensure_job_indexes(database: AsyncDatabase[Any]) -> None:
    collection = database[JOBS_COLLECTION]
    await collection.create_index(
        [("source", 1), ("sourceJobId", 1)],
        unique=True,
        name="uniq_source_source_job_id",
    )
    await collection.create_index(
        [("status", 1), ("country_code", 1), ("posted_at", -1)],
        name="idx_status_job_country_posted",
    )
    await collection.create_index(
        [("status", 1), ("search_country_code", 1), ("posted_at", -1)],
        name="idx_status_search_country_posted",
    )
    await collection.create_index(
        [("status", 1), ("source", 1), ("posted_at", -1)],
        name="idx_status_source_posted",
    )
    await collection.create_index(
        [("status", 1), ("employment_type", 1), ("posted_at", -1)],
        name="idx_status_employment_posted",
    )
    await collection.create_index(
        [("status", 1), ("is_remote", 1), ("posted_at", -1)],
        name="idx_status_remote_posted",
    )
    await collection.create_index(
        [("status", 1), ("last_seen_at", -1)],
        name="idx_status_last_seen",
    )
    await collection.create_index([("title", 1)], name="idx_title")
    await collection.create_index([("company", 1)], name="idx_company")
    logger.info("MongoDB job indexes ensured")

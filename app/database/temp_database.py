"""Secondary MongoDB database access for CLI/tools (alternate db name)."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

from pymongo import AsyncMongoClient
from pymongo.asynchronous.database import AsyncDatabase

from app.core.config import get_settings
from app.database.collection_indexes import ensure_collection_indexes
from app.database.indexes import ensure_job_indexes


@asynccontextmanager
async def open_database(db_name: str) -> AsyncIterator[AsyncDatabase[Any]]:
    settings = get_settings()
    client = AsyncMongoClient(settings.mongo_uri, serverSelectionTimeoutMS=5000)
    database = client[db_name]
    await client.admin.command("ping")
    await ensure_job_indexes(database)
    await ensure_collection_indexes(
        database,
        migrate_target_search_location=settings.allow_collection_target_index_migration,
    )
    try:
        yield database
    finally:
        await client.close()

import logging
from typing import Any

from pymongo import AsyncMongoClient
from pymongo.asynchronous.database import AsyncDatabase
from pymongo.errors import ConnectionFailure, ServerSelectionTimeoutError

from app.core.config import get_settings

logger = logging.getLogger(__name__)


class MongoDB:
    def __init__(self) -> None:
        self._client: AsyncMongoClient[Any] | None = None
        self._database: AsyncDatabase[Any] | None = None

    async def connect(self) -> None:
        settings = get_settings()
        self._client = AsyncMongoClient(
            settings.mongo_uri,
            serverSelectionTimeoutMS=settings.mongo_server_selection_timeout_ms,
        )
        self._database = self._client[settings.mongo_db_name]
        await self._client.admin.command("ping")
        logger.info("MongoDB connected db=%s", settings.mongo_db_name)

    async def disconnect(self) -> None:
        if self._client is not None:
            await self._client.close()
            self._client = None
            self._database = None
            logger.info("MongoDB disconnected")

    @property
    def database(self) -> AsyncDatabase[Any]:
        if self._database is None:
            raise RuntimeError("MongoDB is not connected")
        return self._database

    async def ping(self) -> bool:
        if self._client is None:
            return False
        try:
            await self._client.admin.command("ping")
            return True
        except (ConnectionFailure, ServerSelectionTimeoutError, OSError):
            return False


_mongodb = MongoDB()


def get_mongodb() -> MongoDB:
    return _mongodb


async def get_database() -> AsyncDatabase[Any]:
    return get_mongodb().database

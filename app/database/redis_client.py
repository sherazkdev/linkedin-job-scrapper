import logging

import redis.asyncio as redis

from app.core.config import get_settings

logger = logging.getLogger(__name__)


class RedisClient:
    def __init__(self) -> None:
        self._client: redis.Redis | None = None

    async def connect(self) -> None:
        settings = get_settings()
        self._client = redis.from_url(
            settings.redis_url,
            encoding="utf-8",
            decode_responses=True,
        )
        await self._client.ping()
        logger.info("Redis connected")

    async def disconnect(self) -> None:
        if self._client is not None:
            await self._client.aclose()
            self._client = None
            logger.info("Redis disconnected")

    @property
    def client(self) -> redis.Redis:
        if self._client is None:
            raise RuntimeError("Redis is not connected")
        return self._client

    async def ping(self) -> bool:
        if self._client is None:
            return False
        try:
            return bool(await self._client.ping())
        except (redis.ConnectionError, redis.TimeoutError, OSError):
            return False


_redis_client = RedisClient()


def get_redis_client() -> RedisClient:
    return _redis_client

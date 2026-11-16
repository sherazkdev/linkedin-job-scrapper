"""Derive Celery broker/result URLs from REDIS_URL when not explicitly set."""

from urllib.parse import urlparse, urlunparse


def redis_url_with_db(redis_url: str, db_index: int) -> str:
    parsed = urlparse(redis_url)
    path = f"/{db_index}"
    return urlunparse(parsed._replace(path=path))


def resolve_celery_broker_url(redis_url: str, override: str | None) -> str:
    if override:
        return override
    return redis_url_with_db(redis_url, 1)


def resolve_celery_result_backend(redis_url: str, override: str | None) -> str:
    if override:
        return override
    return redis_url_with_db(redis_url, 2)

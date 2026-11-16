import os
from collections.abc import AsyncIterator

import httpx
import pytest
from httpx import ASGITransport

from app.main import create_app


def pytest_configure() -> None:
    os.environ.setdefault("APP_ENV", "development")
    os.environ.setdefault("LOG_LEVEL", "WARNING")
    os.environ.setdefault("MONGO_URI", "mongodb://mongo_user:change_me_mongo_password@mongodb:27017/?authSource=admin")
    if os.environ.get("RUN_INTEGRATION") == "1":
        os.environ["MONGO_DB_NAME"] = "global_jobs_test"
    else:
        os.environ.setdefault("MONGO_DB_NAME", "global_jobs_test")
    os.environ.setdefault("REDIS_URL", "redis://:change_me_redis_password@redis:6379/0")
    from app.core.config import get_settings

    get_settings.cache_clear()


@pytest.fixture
async def async_client(require_integration: None) -> AsyncIterator[httpx.AsyncClient]:
    app = create_app()
    async with app.router.lifespan_context(app):
        transport = ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            yield client


@pytest.fixture
async def integration_db(require_integration: None) -> AsyncIterator[None]:
    """Start app lifespan so get_mongodb() works in repository-focused tests."""
    app = create_app()
    async with app.router.lifespan_context(app):
        yield


@pytest.fixture
def integration_enabled() -> bool:
    return os.environ.get("RUN_INTEGRATION", "0") == "1"


@pytest.fixture
def require_integration(integration_enabled: bool) -> None:
    if not integration_enabled:
        pytest.skip("Set RUN_INTEGRATION=1 with MongoDB and Redis available")

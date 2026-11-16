import httpx
import pytest
from httpx import ASGITransport

from app.core.config import get_settings
from app.main import create_app


@pytest.mark.asyncio
async def test_internal_monitoring_disabled_without_token(async_client: httpx.AsyncClient) -> None:
    response = await async_client.get("/internal/v1/monitoring/snapshot")
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_internal_monitoring_rejects_bad_token(
    integration_db: None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("INTERNAL_OPS_TOKEN", "test-token-abc")
    get_settings.cache_clear()
    app = create_app()
    async with app.router.lifespan_context(app):
        transport = ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            unauthorized = await client.get(
                "/internal/v1/monitoring/snapshot",
                headers={"X-Internal-Ops-Token": "wrong"},
            )
            assert unauthorized.status_code == 401
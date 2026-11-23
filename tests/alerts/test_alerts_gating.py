import httpx
import pytest
from httpx import ASGITransport

from app.core.config import get_settings
from app.main import create_app


@pytest.mark.asyncio
async def test_alerts_router_absent_when_disabled(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ALERTS_API_ENABLED", "false")
    get_settings.cache_clear()
    app = create_app()
    paths = {getattr(r, "path", "") for r in app.routes}
    assert "/api/v1/alerts/subscribers/register" not in paths
    get_settings.cache_clear()


@pytest.mark.asyncio
async def test_alerts_register_404_when_disabled(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ALERTS_API_ENABLED", "false")
    get_settings.cache_clear()
    app = create_app()
    transport = ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post("/api/v1/alerts/subscribers/register")
        assert resp.status_code == 404
    get_settings.cache_clear()
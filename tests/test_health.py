import httpx
import pytest


def test_liveness_route_registered() -> None:
    """Liveness route is registered without requiring backing services."""
    from app.main import create_app

    app = create_app()
    routes = {getattr(r, "path", None) for r in app.routes}
    assert "/health/live" in routes


@pytest.mark.asyncio
async def test_health_live_integration(
    async_client: httpx.AsyncClient,
    require_integration: None,
) -> None:
    response = await async_client.get("/health/live")
    assert response.status_code == 200
    body = response.json()
    assert body["success"] is True
    assert body["status"] == "live"


@pytest.mark.asyncio
async def test_health_ready_integration(
    async_client: httpx.AsyncClient,
    require_integration: None,
) -> None:
    response = await async_client.get("/health/ready")
    assert response.status_code == 200
    body = response.json()
    assert body["checks"]["mongodb"] is True
    assert body["checks"]["redis"] is True
    assert body["status"] == "ready"

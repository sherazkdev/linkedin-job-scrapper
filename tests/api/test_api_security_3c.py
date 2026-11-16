import httpx
import pytest

from app.core.config import get_settings


@pytest.mark.asyncio
async def test_rejects_oversized_page_size(async_client: httpx.AsyncClient) -> None:
    response = await async_client.get("/api/v1/jobs", params={"page_size": 500})
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_rejects_page_above_configured_max(async_client: httpx.AsyncClient) -> None:
    settings = get_settings()
    response = await async_client.get("/api/v1/jobs", params={"page": settings.jobs_max_page + 1})
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "validation_error"


@pytest.mark.asyncio
async def test_query_string_length_capped(async_client: httpx.AsyncClient) -> None:
    response = await async_client.get("/api/v1/jobs", params={"q": "x" * 201})
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_internal_snapshot_not_found_without_token(async_client: httpx.AsyncClient) -> None:
    response = await async_client.get("/internal/v1/monitoring/snapshot")
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_security_headers_on_api(
    async_client: httpx.AsyncClient,
    require_integration: None,
) -> None:
    response = await async_client.get("/api/v1/jobs", params={"page_size": 1})
    assert response.headers.get("X-Content-Type-Options") == "nosniff"
    assert response.headers.get("Cache-Control") == "no-store"
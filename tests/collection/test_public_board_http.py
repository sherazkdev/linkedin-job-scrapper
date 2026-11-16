import httpx
import pytest

from app.modules.collection.http.client import PublicBoardHttpClient
from app.modules.collection.http.errors import PublicBoardCollectionError, PublicBoardFailureState


@pytest.mark.asyncio
async def test_http_client_maps_404() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(404)

    client = PublicBoardHttpClient(timeout_seconds=5.0, min_interval_seconds=0)
    client._client = httpx.AsyncClient(  # type: ignore[attr-defined]
        transport=httpx.MockTransport(handler),
        base_url="https://boards-api.greenhouse.io",
    )
    with pytest.raises(PublicBoardCollectionError) as exc:
        await client.get_json("https://boards-api.greenhouse.io/v1/boards/missing/jobs")
    assert exc.value.state == PublicBoardFailureState.NOT_FOUND
    await client.aclose()


@pytest.mark.asyncio
async def test_http_client_invalid_json() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=b"not-json")

    client = PublicBoardHttpClient(timeout_seconds=5.0, min_interval_seconds=0)
    client._client = httpx.AsyncClient(  # type: ignore[attr-defined]
        transport=httpx.MockTransport(handler),
        base_url="https://boards-api.greenhouse.io",
    )
    with pytest.raises(PublicBoardCollectionError) as exc:
        await client.get_json("https://boards-api.greenhouse.io/v1/boards/x/jobs")
    assert exc.value.state == PublicBoardFailureState.INVALID_PAYLOAD
    await client.aclose()


@pytest.mark.asyncio
async def test_http_client_rejects_unapproved_host() -> None:
    client = PublicBoardHttpClient(timeout_seconds=5.0, min_interval_seconds=0)
    with pytest.raises(PublicBoardCollectionError) as exc:
        await client.get_json("https://evil.example.com/v1/boards/x/jobs")
    assert exc.value.state == PublicBoardFailureState.INVALID_PAYLOAD
    await client.aclose()
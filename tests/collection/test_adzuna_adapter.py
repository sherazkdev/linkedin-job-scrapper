import json

import httpx
import pytest
from tests.fixture_paths import ADZUNA_US_PAGE1 as FIXTURE

from app.core.config import get_settings
from app.modules.collection.adapters.adzuna import AdzunaJobSourceAdapter
from app.modules.collection.http.client import PublicBoardHttpClient
from app.modules.collection.http.errors import PublicBoardCollectionError, PublicBoardFailureState
from app.modules.collection.market_search.adzuna_parser import adzuna_results_to_raw


def test_parser_keyword_filter_and_ids() -> None:
    payload = json.loads(FIXTURE.read_text(encoding="utf-8"))
    jobs, metrics = adzuna_results_to_raw(
        payload,
        adzuna_country_slug="us",
        search_country_code="US",
        keyword="Software Engineer",
        skip_ids=set(),
        limit=10,
    )
    assert metrics["accepted"] == 1
    assert jobs[0].source_job_id == "adzuna:us:900001"
    assert jobs[0].search_country_code == "US"
    assert jobs[0].country_code is None
    assert jobs[0].job_url.startswith("https://")


@pytest.mark.asyncio
async def test_offline_fetch_success() -> None:
    settings = get_settings()
    adapter = AdzunaJobSourceAdapter(
        settings=settings,
        offline_fixture=FIXTURE,
        live_enabled=False,
    )
    result = await adapter.fetch_jobs(
        country_code="US",
        keyword="Software Engineer",
        limit=5,
        checkpoint=None,
    )
    assert len(result.jobs) == 1
    assert result.metrics["source"] == "adzuna"


@pytest.mark.asyncio
async def test_unsupported_country_empty() -> None:
    settings = get_settings()
    adapter = AdzunaJobSourceAdapter(settings=settings, offline_fixture=FIXTURE)
    result = await adapter.fetch_jobs(
        country_code="PK",
        keyword="engineer",
        limit=5,
        checkpoint=None,
    )
    assert result.jobs == []
    assert result.metrics.get("unsupported_country") == "PK"


@pytest.mark.asyncio
async def test_live_disabled_without_fixture() -> None:
    settings = get_settings()
    adapter = AdzunaJobSourceAdapter(settings=settings, live_enabled=False)
    with pytest.raises(PublicBoardCollectionError) as exc:
        await adapter.fetch_jobs(country_code="US", keyword="engineer", limit=5, checkpoint=None)
    assert exc.value.state == PublicBoardFailureState.DISABLED


@pytest.mark.asyncio
async def test_live_missing_credentials(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ALLOW_LIVE_MARKET_SEARCH_COLLECTION", "true")
    get_settings.cache_clear()
    settings = get_settings()
    adapter = AdzunaJobSourceAdapter(settings=settings, live_enabled=True)
    with pytest.raises(PublicBoardCollectionError) as exc:
        await adapter.fetch_jobs(country_code="US", keyword="engineer", limit=5, checkpoint=None)
    assert exc.value.state == PublicBoardFailureState.FORBIDDEN


@pytest.mark.asyncio
async def test_mocked_http_429(monkeypatch: pytest.MonkeyPatch) -> None:
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(429)

    http = PublicBoardHttpClient(timeout_seconds=5.0, min_interval_seconds=0)
    http._client = httpx.AsyncClient(  # type: ignore[attr-defined]
        transport=httpx.MockTransport(handler),
        base_url="https://api.adzuna.com",
    )
    monkeypatch.setenv("ADZUNA_APP_ID", "test-id")
    monkeypatch.setenv("ADZUNA_APP_KEY", "test-key")
    get_settings.cache_clear()
    settings = get_settings()
    adapter = AdzunaJobSourceAdapter(settings=settings, http=http, live_enabled=True)
    with pytest.raises(PublicBoardCollectionError) as exc:
        await adapter.fetch_jobs(country_code="US", keyword="engineer", limit=5, checkpoint=None)
    assert exc.value.state == PublicBoardFailureState.RATE_LIMITED
    assert exc.value.retryable is True
    await adapter.aclose()


@pytest.mark.asyncio
async def test_pagination_checkpoint() -> None:
    settings = get_settings()
    adapter = AdzunaJobSourceAdapter(
        settings=settings,
        offline_fixture=FIXTURE,
        live_enabled=False,
    )
    first = await adapter.fetch_jobs(
        country_code="US",
        keyword="Software Engineer",
        limit=1,
        checkpoint=None,
    )
    assert "pages_fetched" in first.checkpoint


@pytest.mark.asyncio
async def test_duplicate_skip_ids() -> None:
    payload = json.loads(FIXTURE.read_text(encoding="utf-8"))
    jobs, _ = adzuna_results_to_raw(
        payload,
        adzuna_country_slug="us",
        search_country_code="US",
        keyword="*",
        skip_ids={"adzuna:us:900001"},
        limit=10,
    )
    assert all(j.source_job_id != "adzuna:us:900001" for j in jobs)
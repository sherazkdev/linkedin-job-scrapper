import pytest

from app.modules.collection.adapters.market_search import (
    MarketSearchJobSourceAdapter,
    MarketSearchNotImplementedError,
)
from app.modules.jobs.models.job import JobSource


class _StubMarketAdapter(MarketSearchJobSourceAdapter):
    source = JobSource.FIXTURE

    def provider_id(self) -> str:
        return "stub"

    def map_country_code(self, country_code: str) -> str | None:
        return "us" if country_code == "US" else None

    def default_budget(self):
        from app.modules.collection.adapters.market_search import MarketSearchQueryBudget

        return MarketSearchQueryBudget()


@pytest.mark.asyncio
async def test_unsupported_country_returns_empty() -> None:
    adapter = _StubMarketAdapter()
    result = await adapter.fetch_jobs(
        country_code="PK", keyword="engineer", limit=10, checkpoint=None
    )
    assert result.jobs == []
    assert result.metrics.get("unsupported_country") == "PK"


@pytest.mark.asyncio
async def test_supported_country_raises_not_implemented() -> None:
    adapter = _StubMarketAdapter()
    with pytest.raises(MarketSearchNotImplementedError):
        await adapter.fetch_jobs(country_code="US", keyword="engineer", limit=10, checkpoint=None)
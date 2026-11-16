import pytest

from app.modules.collection.adapters.fixture import FixtureJobSourceAdapter


@pytest.mark.asyncio
async def test_fixture_adapter_contract() -> None:
    adapter = FixtureJobSourceAdapter()
    first = await adapter.fetch_jobs(
        country_code="DE",
        keyword="backend engineer",
        limit=2,
        checkpoint=None,
    )
    assert len(first.jobs) == 2
    assert first.jobs[0].source_job_id.startswith("fixture-de-")
    second = await adapter.fetch_jobs(
        country_code="DE",
        keyword="backend engineer",
        limit=2,
        checkpoint=first.checkpoint,
    )
    assert second.jobs[0].source_job_id != first.jobs[0].source_job_id

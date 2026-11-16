
import pytest
from tests.fixture_paths import GREENHOUSE_SAMPLE as FIXTURE

from app.core.config import get_settings
from app.modules.collection.adapters.greenhouse import GreenhouseJobSourceAdapter
from app.modules.collection.services.normalizer import JobNormalizer
from app.modules.jobs.models.job import JobSource


@pytest.mark.asyncio
async def test_greenhouse_offline_adapter_contract() -> None:
    settings = get_settings()
    adapter = GreenhouseJobSourceAdapter(
        settings=settings,
        board_token="sample",
        offline_fixture=FIXTURE,
        live_enabled=False,
    )
    result = await adapter.fetch_jobs(
        country_code="US",
        keyword="engineer",
        limit=3,
        checkpoint=None,
    )
    await adapter.aclose()
    assert len(result.jobs) == 1
    assert result.jobs[0].source_job_id == "sample:4011001"
    assert result.metrics["source"] == JobSource.GREENHOUSE.value

    job = JobNormalizer(JobSource.GREENHOUSE).normalize(result.jobs[0])
    assert job.source == JobSource.GREENHOUSE
    assert job.title == "Backend Engineer"
    assert job.search_country_code == "US"
    assert job.country_code is not None
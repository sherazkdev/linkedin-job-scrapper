
import pytest
from tests.fixture_paths import LINKEDIN_FIXTURES as FIXTURES

from app.core.config import get_settings
from app.modules.collection.linkedin.adapter import LinkedInJobSourceAdapter


@pytest.mark.asyncio
async def test_linkedin_offline_adapter_fetch() -> None:
    settings = get_settings()
    adapter = LinkedInJobSourceAdapter(
        settings=settings,
        offline_html_root=FIXTURES,
        live_enabled=False,
    )
    result = await adapter.fetch_jobs(
        country_code="DE",
        keyword="backend engineer",
        limit=2,
        checkpoint=None,
    )
    assert len(result.jobs) == 2
    assert result.jobs[0].source_job_id == "9001001"
    assert result.checkpoint["page_index"] >= 1

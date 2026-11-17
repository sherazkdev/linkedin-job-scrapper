"""API list filters: job country vs LinkedIn search market are independent."""

import pytest
from httpx import ASGITransport, AsyncClient

from app.main import create_app
from app.modules.jobs.models.job import JobDataProvenance, JobSource, JobStatus, WorkplaceType


@pytest.mark.asyncio
async def test_us_search_job_invisible_under_country_code_when_geo_resolved_non_us(
    integration_db: None,
) -> None:
    from app.core.config import get_settings
    from app.database.temp_database import open_database

    settings = get_settings()
    async with open_database(settings.mongo_db_name) as db:
        await db.jobs.delete_many({"sourceJobId": "pilot-us-geo-test"})
        await db.jobs.insert_one(
        {
            "source": JobSource.LINKEDIN.value,
            "sourceJobId": "pilot-us-geo-test",
            "title": "Software Engineer",
            "company": "Example",
            "search_country_code": "US",
            "country_code": "DE",
            "location_text": "Berlin, Germany",
            "job_url": "https://www.linkedin.com/jobs/view/1",
            "status": JobStatus.ACTIVE.value,
            "data_provenance": JobDataProvenance.LIVE_API_VERIFIED.value,
            "workplace_type": WorkplaceType.ON_SITE.value,
        }
        )

    app = create_app()
    transport = ASGITransport(app=app)
    async with app.router.lifespan_context(app):
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            by_job = await client.get(
                "/api/v1/jobs",
                params={"source": "linkedin", "country_code": "US"},
            )
            by_search = await client.get(
                "/api/v1/jobs",
                params={"source": "linkedin", "search_country_code": "US"},
            )
    assert by_job.json()["data"]["total"] == 0
    assert by_search.json()["data"]["total"] >= 1
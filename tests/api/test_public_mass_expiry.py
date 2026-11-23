from datetime import UTC, datetime, timedelta

import pytest

from app.database.temp_database import open_database
from app.core.exceptions import NotFoundError
from app.modules.jobs.models.job import JobDataProvenance, JobSource, JobStatus
from app.modules.jobs.repositories.job_repository import JobRepository
from app.modules.jobs.schemas.filters import JobListFilters, JobSort
from app.modules.jobs.services.job_service import JobService


@pytest.mark.asyncio
async def test_when_all_jobs_exceed_max_age_public_views_empty(integration_db: None) -> None:
    now = datetime.now(UTC)
    old = now - timedelta(days=30)
    async with open_database("global_jobs_test") as database:
        await database["jobs"].delete_many({})
        await database["jobs"].insert_many(
            [
                {
                    "source": JobSource.LINKEDIN.value,
                    "sourceJobId": f"old-{i}",
                    "title": f"Role {i}",
                    "company": "Co",
                    "search_country_code": "US",
                    "status": JobStatus.ACTIVE.value,
                    "data_provenance": JobDataProvenance.LIVE_API_VERIFIED.value,
                    "employment_type": "full_time",
                    "workplace_type": "remote",
                    "job_url": f"https://example.org/{i}",
                    "posted_at": old,
                    "first_seen_at": old,
                    "last_seen_at": now,
                }
                for i in range(3)
            ]
        )
        repo = JobRepository(database)
        service = JobService(repo)
        stats = await service.get_stats()
        assert stats.total_active == 0
        countries = await service.list_countries()
        assert sum(c.active_jobs for c in countries["job_countries"]) == 0
        listed, total = await repo.search_jobs(
            filters=JobListFilters(sort=JobSort.POSTED_AT_DESC, status=JobStatus.ACTIVE),
            page=1,
            page_size=20,
            public_listing_max_age_days=7,
        )
        assert total == 0
        assert listed == []
        doc = await repo.get_by_id(str((await database["jobs"].find_one({}))["_id"]))
        assert doc is not None
        with pytest.raises(NotFoundError):
            await service.get_job(str(doc["_id"]))
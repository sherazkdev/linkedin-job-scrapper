from datetime import UTC, datetime, timedelta

import pytest

from app.database.temp_database import open_database
from app.modules.jobs.models.job import JobSource, JobStatus
from app.modules.jobs.repositories.job_repository import JobRepository
from app.modules.jobs.schemas.filters import JobListFilters, JobSort


@pytest.mark.asyncio
async def test_posted_at_desc_orders_by_first_seen_then_source_job_id(integration_db: None) -> None:
    now = datetime.now(UTC)
    async with open_database("global_jobs_test") as database:
        await database["jobs"].delete_many({})
        await database["jobs"].insert_many(
            [
                {
                    "source": JobSource.LINKEDIN.value,
                    "sourceJobId": "b-job",
                    "title": "B",
                    "company": "Co",
                    "search_country_code": "US",
                    "status": JobStatus.ACTIVE.value,
                    "employment_type": "full_time",
                    "workplace_type": "remote",
                    "job_url": "https://example.org/b",
                    "posted_at": None,
                    "first_seen_at": now - timedelta(hours=1),
                    "last_seen_at": now,
                },
                {
                    "source": JobSource.LINKEDIN.value,
                    "sourceJobId": "a-job",
                    "title": "A",
                    "company": "Co",
                    "search_country_code": "US",
                    "status": JobStatus.ACTIVE.value,
                    "employment_type": "full_time",
                    "workplace_type": "remote",
                    "job_url": "https://example.org/a",
                    "posted_at": None,
                    "first_seen_at": now,
                    "last_seen_at": now,
                },
            ]
        )
        repo = JobRepository(database)
        filters = JobListFilters(sort=JobSort.POSTED_AT_DESC, status=JobStatus.ACTIVE)
        items, total = await repo.search_jobs(filters=filters, page=1, page_size=10)
        assert total == 2
        ids = [row["sourceJobId"] for row in items]
        assert ids[0] == "a-job"
        assert ids[1] == "b-job"
from datetime import UTC, datetime, timedelta

import pytest

from app.database.temp_database import open_database
from app.modules.jobs.models.job import JobDataProvenance, JobSource, JobStatus
from app.modules.jobs.repositories.job_repository import JobRepository


@pytest.mark.asyncio
async def test_stats_excludes_jobs_past_public_max_age(integration_db: None) -> None:
    now = datetime.now(UTC)
    async with open_database("global_jobs_test") as database:
        await database["jobs"].delete_many({})
        await database["jobs"].insert_many(
            [
                {
                    "source": JobSource.LINKEDIN.value,
                    "sourceJobId": "fresh",
                    "title": "A",
                    "company": "Co",
                    "search_country_code": "US",
                    "status": JobStatus.ACTIVE.value,
                    "data_provenance": JobDataProvenance.LIVE_API_VERIFIED.value,
                    "employment_type": "full_time",
                    "workplace_type": "remote",
                    "job_url": "https://example.org/f",
                    "posted_at": now,
                    "first_seen_at": now,
                    "last_seen_at": now,
                },
                {
                    "source": JobSource.LINKEDIN.value,
                    "sourceJobId": "old",
                    "title": "B",
                    "company": "Co",
                    "search_country_code": "US",
                    "status": JobStatus.ACTIVE.value,
                    "data_provenance": JobDataProvenance.LIVE_API_VERIFIED.value,
                    "employment_type": "full_time",
                    "workplace_type": "remote",
                    "job_url": "https://example.org/o",
                    "posted_at": now - timedelta(days=10),
                    "first_seen_at": now - timedelta(days=10),
                    "last_seen_at": now,
                },
            ]
        )
        repo = JobRepository(database)
        stats = await repo.aggregate_public_stats()
        assert stats["total_active"] == 1
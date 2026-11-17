import pytest

from app.database.indexes import JOBS_COLLECTION
from app.database.temp_database import open_database
from app.modules.jobs.models.job import JobDataProvenance, JobSource, JobStatus
from app.modules.promotion.publication_sync import analyze_publication_sync


@pytest.mark.asyncio
async def test_no_deprecate_when_pilot_still_active_live_verified(integration_db: None) -> None:
    """Collection pause / validation gap must not plan production removal."""
    pilot_db = "global_jobs_test_pilot"
    prod_db = "global_jobs_test"
    async with open_database(pilot_db) as pilot, open_database(prod_db) as production:
        await pilot[JOBS_COLLECTION].delete_many({})
        await production[JOBS_COLLECTION].delete_many({})
        doc = {
            "source": JobSource.LINKEDIN.value,
            "sourceJobId": "keep-1",
            "title": "Engineer",
            "company": "Co",
            "status": JobStatus.ACTIVE.value,
            "data_provenance": JobDataProvenance.LIVE_API_VERIFIED.value,
            "search_country_code": "GB",
            "job_url": "",  # fails ELIGIBLE_QUERY but still active live row in pilot
            "posted_at": None,
        }
        await pilot[JOBS_COLLECTION].insert_one(doc)
        await production[JOBS_COLLECTION].insert_one(
            {
                **doc,
                "job_url": "https://www.linkedin.com/jobs/view/keep-1",
                "posted_at": doc.get("posted_at"),
            }
        )
        plan = await analyze_publication_sync(pilot, production, enforce_db_names=False)
        assert plan["sync_plan"]["would_deprecate_count"] == 0
        assert "keep-1" in plan["sync_plan"]["would_retain_despite_not_eligible"]


@pytest.mark.asyncio
async def test_deprecate_when_pilot_marks_stale(integration_db: None) -> None:
    pilot_db = "global_jobs_test_pilot"
    prod_db = "global_jobs_test"
    async with open_database(pilot_db) as pilot, open_database(prod_db) as production:
        await pilot[JOBS_COLLECTION].delete_many({})
        await production[JOBS_COLLECTION].delete_many({})
        base = {
            "source": JobSource.LINKEDIN.value,
            "sourceJobId": "gone-1",
            "title": "Engineer",
            "company": "Co",
            "search_country_code": "GB",
            "job_url": "https://www.linkedin.com/jobs/view/gone-1",
        }
        await pilot[JOBS_COLLECTION].insert_one(
            {**base, "status": JobStatus.STALE.value, "data_provenance": "live_api_verified"}
        )
        await production[JOBS_COLLECTION].insert_one(
            {**base, "status": JobStatus.ACTIVE.value, "data_provenance": "live_api_verified"}
        )
        plan = await analyze_publication_sync(pilot, production, enforce_db_names=False)
        assert "gone-1" in plan["sync_plan"]["would_deprecate_ids"]
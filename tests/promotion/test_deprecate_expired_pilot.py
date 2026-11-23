import pytest

from app.database.indexes import JOBS_COLLECTION
from app.database.temp_database import open_database
from app.modules.jobs.models.job import JobDataProvenance, JobSource, JobStatus
from app.modules.promotion.publication_sync import (
    analyze_publication_sync,
    apply_production_deprecations,
)


@pytest.mark.asyncio
async def test_deprecate_when_pilot_expired(integration_db: None) -> None:
    pilot_db = "global_jobs_test_pilot"
    prod_db = "global_jobs_test"
    async with open_database(pilot_db) as pilot, open_database(prod_db) as production:
        await pilot[JOBS_COLLECTION].delete_many({})
        await production[JOBS_COLLECTION].delete_many({})
        base = {
            "source": JobSource.LINKEDIN.value,
            "sourceJobId": "old-1",
            "title": "Engineer",
            "company": "Co",
            "search_country_code": "GB",
            "job_url": "https://www.linkedin.com/jobs/view/old-1",
            "data_provenance": JobDataProvenance.LIVE_API_VERIFIED.value,
        }
        await pilot[JOBS_COLLECTION].insert_one(
            {**base, "status": JobStatus.EXPIRED.value, "expiry_reason": "public_listing_max_age"}
        )
        await production[JOBS_COLLECTION].insert_one({**base, "status": JobStatus.ACTIVE.value})
        plan = await analyze_publication_sync(pilot, production, enforce_db_names=False)
        assert "old-1" in plan["sync_plan"]["would_deprecate_ids"]
        reasons = {r["sourceJobId"]: r["reason"] for r in plan["sync_plan"]["would_deprecate_reasons"]}
        assert reasons["old-1"] == "pilot_status_expired"
        result = await apply_production_deprecations(
            production,
            source_job_ids=["old-1"],
            batch_id="t1",
            reasons_by_id=reasons,
        )
        assert result["deprecated_count"] == 1
        prod = await production[JOBS_COLLECTION].find_one({"sourceJobId": "old-1"})
        assert prod is not None
        assert prod["status"] == JobStatus.EXPIRED.value
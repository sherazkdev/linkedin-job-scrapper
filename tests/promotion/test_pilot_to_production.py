from datetime import UTC, datetime

import pytest

from app.database.indexes import JOBS_COLLECTION
from app.database.temp_database import open_database
from app.modules.jobs.models.job import JobDataProvenance, JobSource, JobStatus
from app.modules.promotion.pilot_to_production import (
    ELIGIBLE_QUERY,
    analyze_promotion,
    apply_promotion,
    count_eligible,
    new_batch_id,
    rollback_batch,
    write_backup,
)


def _job(source_job_id: str, *, search_cc: str = "GB") -> dict:
    return {
        "source": JobSource.LINKEDIN.value,
        "sourceJobId": source_job_id,
        "title": "Software Engineer",
        "company": "Pilot Co",
        "status": JobStatus.ACTIVE.value,
        "data_provenance": JobDataProvenance.LIVE_API_VERIFIED.value,
        "search_country_code": search_cc,
        "country_code": search_cc,
        "job_url": f"https://www.linkedin.com/jobs/view/{source_job_id}",
        "posted_at": datetime.now(UTC),
        "first_seen_at": datetime.now(UTC),
    }


@pytest.mark.asyncio
async def test_eligible_count_and_dry_run_analysis(integration_db: None) -> None:
    pilot_db = "global_jobs_test_pilot"
    prod_db = "global_jobs_test"
    async with open_database(pilot_db) as pilot, open_database(prod_db) as production:
        await pilot[JOBS_COLLECTION].delete_many({})
        await production[JOBS_COLLECTION].delete_many({})
        await pilot[JOBS_COLLECTION].insert_one(_job("111"))
        await pilot[JOBS_COLLECTION].insert_one(_job("222"))
        await pilot[JOBS_COLLECTION].insert_one(
            {**_job("offline"), "data_provenance": JobDataProvenance.SYNTHETIC_FIXTURE.value}
        )
        assert await count_eligible(pilot) == 2
        report = await analyze_promotion(pilot, production)
        assert report["eligible_live_verified"] == 2
        assert report["dry_run_would_create"] == 2


@pytest.mark.asyncio
async def test_apply_and_rollback_is_idempotent(integration_db: None) -> None:
    pilot_db = "global_jobs_test_pilot"
    prod_db = "global_jobs_test"
    async with open_database(pilot_db) as pilot, open_database(prod_db) as production:
        await pilot[JOBS_COLLECTION].delete_many({})
        await production[JOBS_COLLECTION].delete_many({})
        await pilot[JOBS_COLLECTION].insert_one(_job("promo-1"))
        docs = await pilot[JOBS_COLLECTION].find(ELIGIBLE_QUERY).to_list(length=10)
        batch_id = new_batch_id()
        backup = await write_backup(docs, __import__("pathlib").Path("evidence/promotion_backups/test.json"), batch_id=batch_id)  # noqa: PTH
        r1 = await apply_promotion(
            pilot_db=pilot, production_db=production, batch_id=batch_id, docs=docs
        )
        assert r1["created"] == 1
        r2 = await apply_promotion(
            pilot_db=pilot, production_db=production, batch_id=batch_id, docs=docs
        )
        assert r2["updated"] == 1
        assert r2["created"] == 0
        assert await production[JOBS_COLLECTION].count_documents({}) == 1
        rb = await rollback_batch(production, batch_id=batch_id, backup_path=backup)
        assert rb["removed_created"] == 1
        assert await production[JOBS_COLLECTION].count_documents({}) == 0
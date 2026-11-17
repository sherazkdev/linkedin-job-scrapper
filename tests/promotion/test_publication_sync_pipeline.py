from datetime import UTC, datetime, timedelta

import pytest

from app.database.indexes import JOBS_COLLECTION
from app.database.temp_database import open_database
from app.modules.jobs.models.job import JobDataProvenance, JobSource, JobStatus
from app.modules.promotion.monitoring import collect_publication_metrics
from app.modules.promotion.pilot_to_production import ELIGIBLE_QUERY, apply_promotion, new_batch_id
from app.modules.promotion.publication_sync import (
    analyze_publication_sync,
    apply_production_deprecations,
)


def _job(
    source_job_id: str,
    *,
    search_cc: str = "GB",
    status: JobStatus = JobStatus.ACTIVE,
) -> dict:
    now = datetime.now(UTC)
    return {
        "source": JobSource.LINKEDIN.value,
        "sourceJobId": source_job_id,
        "title": "Software Engineer",
        "company": "Co",
        "status": status.value,
        "data_provenance": JobDataProvenance.LIVE_API_VERIFIED.value,
        "search_country_code": search_cc,
        "job_url": f"https://www.linkedin.com/jobs/view/{source_job_id}",
        "posted_at": now,
        "first_seen_at": now,
        "last_seen_at": now,
    }


@pytest.mark.asyncio
async def test_offline_sync_pipeline_create_update_deprecate(integration_db: None) -> None:
    pilot_db = "global_jobs_test_pilot"
    prod_db = "global_jobs_test"
    async with open_database(pilot_db) as pilot, open_database(prod_db) as production:
        await pilot[JOBS_COLLECTION].delete_many({})
        await production[JOBS_COLLECTION].delete_many({})

        await pilot[JOBS_COLLECTION].insert_one(_job("sync-1"))
        await pilot[JOBS_COLLECTION].insert_one(_job("sync-2"))
        docs = await pilot[JOBS_COLLECTION].find(ELIGIBLE_QUERY).to_list(length=10)
        batch_id = new_batch_id()
        await apply_promotion(
            pilot_db=pilot, production_db=production, batch_id=batch_id, docs=docs
        )
        assert await production[JOBS_COLLECTION].count_documents(ELIGIBLE_QUERY) == 2

        plan = await analyze_publication_sync(pilot, production, enforce_db_names=False)
        assert plan["sync_plan"]["would_create_count"] == 0
        assert plan["sync_plan"]["would_deprecate_count"] == 0

        # Pilot drops sync-2 from eligibility; production should plan deprecation
        await pilot[JOBS_COLLECTION].update_one(
            {"sourceJobId": "sync-2"},
            {"$set": {"status": JobStatus.STALE.value}},
        )
        await pilot[JOBS_COLLECTION].insert_one(_job("sync-3"))
        plan2 = await analyze_publication_sync(pilot, production, enforce_db_names=False)
        assert plan2["sync_plan"]["would_create_count"] == 1
        assert "sync-3" in plan2["sync_plan"]["would_create_ids"]
        assert plan2["sync_plan"]["would_deprecate_count"] == 1
        assert "sync-2" in plan2["sync_plan"]["would_deprecate_ids"]

        dep_batch = new_batch_id()
        dep = await apply_production_deprecations(
            production, source_job_ids=["sync-2"], batch_id=dep_batch
        )
        assert dep["deprecated_count"] == 1
        stale = await production[JOBS_COLLECTION].find_one({"sourceJobId": "sync-2"})
        assert stale is not None
        assert stale["status"] == JobStatus.STALE.value

        metrics = await collect_publication_metrics(pilot_db=pilot, production_db=production)
        assert metrics["job_freshness"]["pilot_eligible_active"] == 2
        assert metrics["publication_sync"]["would_create"] == 1


@pytest.mark.asyncio
async def test_publication_lag_detected(integration_db: None) -> None:
    pilot_db = "global_jobs_test_pilot"
    prod_db = "global_jobs_test"
    async with open_database(pilot_db) as pilot, open_database(prod_db) as production:
        await pilot[JOBS_COLLECTION].delete_many({})
        await production[JOBS_COLLECTION].delete_many({})
        now = datetime.now(UTC)
        await pilot[JOBS_COLLECTION].insert_one(
            {
                **_job("lag-1"),
                "last_seen_at": now,
            }
        )
        await production[JOBS_COLLECTION].insert_one(
            {
                **_job("lag-1"),
                "last_seen_at": now - timedelta(hours=3),
                "promoted_from_pilot_at": now - timedelta(hours=3),
            }
        )
        plan = await analyze_publication_sync(pilot, production, enforce_db_names=False)
        samples = plan["sync_plan"]["publication_lag_samples"]
        assert any(s["sourceJobId"] == "lag-1" for s in samples)
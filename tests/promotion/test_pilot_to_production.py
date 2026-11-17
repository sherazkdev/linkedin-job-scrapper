from datetime import UTC, datetime
from pathlib import Path

import pytest

from app.database.indexes import JOBS_COLLECTION
from app.database.temp_database import open_database
from app.modules.jobs.models.job import JobDataProvenance, JobSource, JobStatus
from app.modules.promotion.pilot_to_production import (
    ELIGIBLE_QUERY,
    PRODUCTION_DB_NAME,
    PILOT_DB_NAME,
    analyze_promotion,
    apply_promotion,
    assert_promotion_database_names,
    count_eligible,
    new_batch_id,
    rollback_batch,
    validate_eligible_jobs,
    write_backup,
)


def _job(source_job_id: str, *, search_cc: str = "GB", title: str = "Software Engineer") -> dict:
    return {
        "source": JobSource.LINKEDIN.value,
        "sourceJobId": source_job_id,
        "title": title,
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
async def test_database_name_assertions() -> None:
    assert_promotion_database_names(pilot_db=PILOT_DB_NAME, production_db=PRODUCTION_DB_NAME)
    with pytest.raises(ValueError):
        assert_promotion_database_names(pilot_db="global_jobs_test", production_db=PRODUCTION_DB_NAME)


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
        v = await validate_eligible_jobs(pilot)
        assert v["validation_ok"] is True
        assert v["eligible_count"] == 2
        report = await analyze_promotion(pilot, production)
        assert report["eligible_live_verified"] == 2
        assert report["dry_run_would_create"] == 2


@pytest.mark.asyncio
async def test_apply_create_and_idempotent_reapply(integration_db: None) -> None:
    pilot_db = "global_jobs_test_pilot"
    prod_db = "global_jobs_test"
    async with open_database(pilot_db) as pilot, open_database(prod_db) as production:
        await pilot[JOBS_COLLECTION].delete_many({})
        await production[JOBS_COLLECTION].delete_many({})
        await pilot[JOBS_COLLECTION].insert_one(_job("promo-1"))
        docs = await pilot[JOBS_COLLECTION].find(ELIGIBLE_QUERY).to_list(length=10)
        batch_id = new_batch_id()
        r1 = await apply_promotion(
            pilot_db=pilot, production_db=production, batch_id=batch_id, docs=docs
        )
        assert r1["created"] == 1
        r2 = await apply_promotion(
            pilot_db=pilot, production_db=production, batch_id=batch_id + "-2", docs=docs
        )
        assert r2["updated"] == 1
        assert r2["created"] == 0
        assert await production[JOBS_COLLECTION].count_documents({}) == 1


@pytest.mark.asyncio
async def test_rollback_restores_prior_production_not_pilot(integration_db: None) -> None:
    pilot_db = "global_jobs_test_pilot"
    prod_db = "global_jobs_test"
    async with open_database(pilot_db) as pilot, open_database(prod_db) as production:
        await pilot[JOBS_COLLECTION].delete_many({})
        await production[JOBS_COLLECTION].delete_many({})
        await production[JOBS_COLLECTION].insert_one(
            {
                **_job("shared-1", title="Production Original Title"),
                "custom_production_field": "keep-me",
            }
        )
        await pilot[JOBS_COLLECTION].insert_one(_job("shared-1", title="Pilot New Title"))
        docs = await pilot[JOBS_COLLECTION].find(ELIGIBLE_QUERY).to_list(length=10)
        batch_id = new_batch_id()
        prior = await production[JOBS_COLLECTION].find_one({"sourceJobId": "shared-1"})
        backup_path = Path("evidence/promotion_backups/test-rollback.json")
        await write_backup(
            docs,
            backup_path,
            batch_id=batch_id,
            production_prior_docs=[prior] if prior else [],
        )
        await apply_promotion(
            pilot_db=pilot, production_db=production, batch_id=batch_id, docs=docs
        )
        after = await production[JOBS_COLLECTION].find_one({"sourceJobId": "shared-1"})
        assert after is not None
        assert after["title"] == "Pilot New Title"
        rb = await rollback_batch(production, batch_id=batch_id, backup_path=backup_path)
        assert rb["restored_updated"] == 1
        restored = await production[JOBS_COLLECTION].find_one({"sourceJobId": "shared-1"})
        assert restored is not None
        assert restored["title"] == "Production Original Title"
        assert restored.get("custom_production_field") == "keep-me"
        assert "promotion_batch_id" not in restored


@pytest.mark.asyncio
async def test_rollback_deletes_created_only(integration_db: None) -> None:
    pilot_db = "global_jobs_test_pilot"
    prod_db = "global_jobs_test"
    async with open_database(pilot_db) as pilot, open_database(prod_db) as production:
        await pilot[JOBS_COLLECTION].delete_many({})
        await production[JOBS_COLLECTION].delete_many({})
        await pilot[JOBS_COLLECTION].insert_one(_job("new-only"))
        docs = await pilot[JOBS_COLLECTION].find(ELIGIBLE_QUERY).to_list(length=10)
        batch_id = new_batch_id()
        backup_path = Path("evidence/promotion_backups/test-create-rollback.json")
        await write_backup(docs, backup_path, batch_id=batch_id)
        await apply_promotion(
            pilot_db=pilot, production_db=production, batch_id=batch_id, docs=docs
        )
        assert await production[JOBS_COLLECTION].count_documents({}) == 1
        rb = await rollback_batch(production, batch_id=batch_id, backup_path=backup_path)
        assert rb["removed_created"] == 1
        assert await production[JOBS_COLLECTION].count_documents({}) == 0


@pytest.mark.asyncio
async def test_partial_failure_continues(integration_db: None) -> None:
    pilot_db = "global_jobs_test_pilot"
    prod_db = "global_jobs_test"
    async with open_database(pilot_db) as pilot, open_database(prod_db) as production:
        await pilot[JOBS_COLLECTION].delete_many({})
        await production[JOBS_COLLECTION].delete_many({})
        await pilot[JOBS_COLLECTION].insert_one(_job("ok-1"))
        docs = await pilot[JOBS_COLLECTION].find(ELIGIBLE_QUERY).to_list(length=10)
        docs.append({"source": JobSource.LINKEDIN.value, "sourceJobId": ""})
        batch_id = new_batch_id()
        result = await apply_promotion(
            pilot_db=pilot, production_db=production, batch_id=batch_id, docs=docs
        )
        assert result["created"] == 1
        assert "missing_sourceJobId" in result["errors"]
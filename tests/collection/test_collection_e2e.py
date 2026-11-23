from datetime import UTC, datetime

import pytest

from app.core.config import get_settings
from app.database.temp_database import open_database
from app.modules.collection.factory import build_collector
from app.modules.collection.repositories.checkpoint_repository import CheckpointRepository
from app.modules.collection.repositories.target_repository import TargetRepository
from app.modules.jobs.models.job import JobSource
from app.modules.jobs.repositories.job_repository import JobRepository


@pytest.mark.asyncio
async def test_fixture_collection_pipeline(integration_db: None) -> None:
    settings = get_settings()
    db_name = "global_jobs_test"
    async with open_database(db_name) as database:
        await TargetRepository(database).ensure_defaults()
        collector = build_collector(database, settings, JobSource.FIXTURE)

        first = await collector.collect(
            source=JobSource.FIXTURE,
            country_code="DE",
            keyword="backend engineer",
            max_jobs=3,
            dry_run=False,
            run_owner="test-e2e-1",
        )
        assert first["stats"]["created_count"] == 3

        second = await collector.collect(
            source=JobSource.FIXTURE,
            country_code="DE",
            keyword="backend engineer",
            max_jobs=3,
            dry_run=False,
            run_owner="test-e2e-2",
        )
        assert second["stats"]["created_count"] == 3

        checkpoint = await CheckpointRepository(database).load(
            source=JobSource.FIXTURE,
            country_code="DE",
            keyword="backend engineer",
        )
        assert checkpoint is not None
        assert checkpoint.get("offset", 0) >= 3


@pytest.mark.asyncio
async def test_first_seen_preserved_on_update(integration_db: None) -> None:
    settings = get_settings()
    db_name = "global_jobs_test"
    async with open_database(db_name) as database:
        targets = TargetRepository(database)
        await targets.ensure_defaults()
        await database["collection_targets"].update_many(
            {
                "source": JobSource.FIXTURE.value,
                "country_code": "SE",
                "keyword": "platform engineer",
            },
            {"$set": {"lock_owner": None, "locked_until": None, "enabled": True}},
        )
        collector = build_collector(database, settings, JobSource.FIXTURE)
        await collector.collect(
            source=JobSource.FIXTURE,
            country_code="SE",
            keyword="platform engineer",
            max_jobs=1,
            dry_run=False,
            run_owner="test-first-seen",
        )
        repo = JobRepository(database)
        doc = await database["jobs"].find_one(
            {"source": JobSource.FIXTURE.value, "country_code": "SE"}
        )
        assert doc is not None
        first_seen = doc["first_seen_at"]

        # Simulate content update via direct repository upsert
        from app.modules.jobs.models.job import JobDocument, JobStatus

        job = JobDocument(
            source=JobSource.FIXTURE,
            source_job_id=doc["sourceJobId"],
            title=doc["title"] + " (rev)",
            company=doc["company"],
            search_country_code=doc.get("search_country_code") or doc["country_code"],
            country_code=doc.get("country_code"),
            location_text=doc.get("location_text"),
            city=doc.get("city"),
            description=doc["description"],
            employment_type=doc["employment_type"],
            workplace_type=doc["workplace_type"],
            job_url=doc["job_url"],
            posted_at=doc["posted_at"],
            first_seen_at=datetime.now(UTC),
            last_seen_at=datetime.now(UTC),
            status=JobStatus.ACTIVE,
        )
        updated, outcome, _reactivated = await repo.upsert_job_tracked(job)
        assert outcome.value == "updated"
        assert updated["first_seen_at"] == first_seen


@pytest.mark.asyncio
async def test_concurrent_lock_blocks_second_run(integration_db: None) -> None:
    db_name = "global_jobs_test"
    async with open_database(db_name) as database:
        targets = TargetRepository(database)
        await targets.ensure_defaults()
        acquired = await targets.try_acquire_lock(
            source=JobSource.FIXTURE,
            country_code="US",
            keyword="data engineer",
            owner="holder",
            lease_seconds=60,
        )
        assert acquired is not None
        blocked = await targets.try_acquire_lock(
            source=JobSource.FIXTURE,
            country_code="US",
            keyword="data engineer",
            owner="other",
            lease_seconds=60,
        )
        assert blocked is None
        await targets.release_lock(acquired["_id"], "holder")

import asyncio
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, patch

import pytest

from app.core.config import get_settings
from app.database.temp_database import open_database
from app.modules.collection.factory import build_collector
from app.modules.collection.repositories.run_repository import RunRepository
from app.modules.collection.repositories.target_repository import TargetRepository, lock_is_active
from app.modules.collection.services.collector import CollectionLockError, JobCollector
from app.modules.collection.services.run_service import CollectionRunService
from app.modules.jobs.models.job import JobSource


@pytest.mark.asyncio
async def test_stale_lease_allows_new_owner(integration_db: None) -> None:
    async with open_database("global_jobs_test") as database:
        repo = TargetRepository(database)
        await repo.ensure_defaults()
        first = await repo.try_acquire_lock(
            source=JobSource.FIXTURE,
            country_code="PK",
            keyword="software engineer",
            owner="owner-a",
            lease_seconds=120,
        )
        assert first is not None
        expired = datetime.now(UTC) - timedelta(seconds=5)
        await database["collection_targets"].update_one(
            {"_id": first["_id"]},
            {"$set": {"locked_until": expired}},
        )
        second = await repo.try_acquire_lock(
            source=JobSource.FIXTURE,
            country_code="PK",
            keyword="software engineer",
            owner="owner-b",
            lease_seconds=120,
        )
        assert second is not None
        assert second["lock_owner"] == "owner-b"
        await repo.release_lock(second["_id"], "owner-b")


@pytest.mark.asyncio
async def test_concurrent_live_lock_rejects_second_collector(integration_db: None) -> None:
    settings = get_settings()
    async with open_database("global_jobs_test") as database:
        targets = TargetRepository(database)
        runs = RunRepository(database)
        run_service = CollectionRunService(runs)
        await targets.ensure_defaults()
        lock_doc = await targets.try_acquire_lock(
            source=JobSource.FIXTURE,
            country_code="US",
            keyword="data engineer",
            owner="live-worker",
            lease_seconds=300,
        )
        assert lock_doc is not None
        run = await run_service.start(
            source=JobSource.FIXTURE,
            country_code="US",
            keyword="data engineer",
            dry_run=False,
        )
        collector = build_collector(database, settings, JobSource.FIXTURE)
        with pytest.raises(CollectionLockError):
            await collector.collect(
                source=JobSource.FIXTURE,
                country_code="US",
                keyword="data engineer",
                max_jobs=1,
                dry_run=False,
                run_owner="other-worker",
            )
        await run_service.cancel_active_run(run.run_id, error_summary="test_cleanup")
        await targets.release_lock(lock_doc["_id"], "live-worker")


@pytest.mark.asyncio
async def test_orphaned_running_run_cleared_on_collect(integration_db: None) -> None:
    settings = get_settings()
    async with open_database("global_jobs_test") as database:
        targets = TargetRepository(database)
        runs = RunRepository(database)
        run_service = CollectionRunService(runs)
        await targets.ensure_defaults()
        orphan = await run_service.start(
            source=JobSource.FIXTURE,
            country_code="DE",
            keyword="backend engineer",
            dry_run=False,
        )
        collector = build_collector(database, settings, JobSource.FIXTURE)
        result = await collector.collect(
            source=JobSource.FIXTURE,
            country_code="DE",
            keyword="backend engineer",
            max_jobs=1,
            dry_run=False,
            run_owner="recovery-collector",
        )
        assert result["run_id"] != orphan.run_id
        cancelled = await database["collection_runs"].find_one({"run_id": orphan.run_id})
        assert cancelled is not None
        assert cancelled["status"] == "cancelled"
        target = await targets.find_target(
            source=JobSource.FIXTURE,
            country_code="DE",
            keyword="backend engineer",
        )
        assert target is not None
        assert not lock_is_active(target)


@pytest.mark.asyncio
async def test_running_run_guard_scoped_by_search_location(integration_db: None) -> None:
    async with open_database("global_jobs_test") as database:
        runs = RunRepository(database)
        run_service = CollectionRunService(runs)
        targets = TargetRepository(database)
        await targets.upsert_target(
            source=JobSource.LINKEDIN,
            country_code="PK",
            keyword="junior erp consultant",
            search_location="islamabad, pakistan",
            enabled=True,
        )
        await targets.upsert_target(
            source=JobSource.LINKEDIN,
            country_code="PK",
            keyword="junior erp consultant",
            search_location="",
            enabled=True,
        )
        isb_run = await run_service.start(
            source=JobSource.LINKEDIN,
            country_code="PK",
            keyword="junior erp consultant",
            dry_run=False,
            search_location="islamabad, pakistan",
        )
        assert isb_run.run_id
        country_active = await run_service.get_running(
            source=JobSource.LINKEDIN,
            country_code="PK",
            keyword="junior erp consultant",
            search_location=None,
        )
        assert country_active is None
        isb_active = await run_service.get_running(
            source=JobSource.LINKEDIN,
            country_code="PK",
            keyword="junior erp consultant",
            search_location="islamabad, pakistan",
        )
        assert isb_active is not None
        assert isb_active["run_id"] == isb_run.run_id
        await run_service.cancel_active_run(isb_run.run_id, error_summary="test_cleanup")


@pytest.mark.asyncio
async def test_cancellation_releases_lock_and_marks_run_cancelled(integration_db: None) -> None:
    settings = get_settings()
    async with open_database("global_jobs_test") as database:
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
        assert isinstance(collector, JobCollector)
        with patch.object(
            collector,
            "_fetch_and_process",
            new=AsyncMock(side_effect=asyncio.CancelledError()),
        ):
            with pytest.raises(asyncio.CancelledError):
                await collector.collect(
                    source=JobSource.FIXTURE,
                    country_code="SE",
                    keyword="platform engineer",
                    max_jobs=1,
                    dry_run=False,
                    run_owner="cancel-test",
                )
        target = await TargetRepository(database).find_target(
            source=JobSource.FIXTURE,
            country_code="SE",
            keyword="platform engineer",
        )
        assert target is not None
        assert target.get("lock_owner") is None
        latest = (
            await database["collection_runs"]
            .find({"keyword": "platform engineer", "country_code": "SE"})
            .sort("started_at", -1)
            .limit(1)
            .to_list(1)
        )
        assert latest
        assert latest[0]["status"] == "cancelled"
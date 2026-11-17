from datetime import UTC, datetime

import pytest

from app.database.temp_database import open_database
from app.modules.collection.repositories.target_repository import TargetRepository
from app.modules.jobs.models.job import JobSource


@pytest.mark.asyncio
async def test_mark_success_persists_last_run_stats(integration_db: None) -> None:
    async with open_database("global_jobs_test") as database:
        repo = TargetRepository(database)
        await repo.ensure_defaults()
        doc = await repo.try_acquire_lock(
            source=JobSource.FIXTURE,
            country_code="GB",
            keyword="software engineer",
            owner="test-worker",
            lease_seconds=60,
        )
        assert doc is not None
        await repo.mark_success(
            doc["_id"],
            cooldown_seconds=0,
            last_run_stats={
                "collected_count": 3,
                "created_count": 2,
                "duration_seconds": 12.5,
                "run_id": "run-abc",
            },
        )
        stored = await database["collection_targets"].find_one({"_id": doc["_id"]})
        assert stored is not None
        assert stored["last_run_collected_count"] == 3
        assert stored["last_run_created_count"] == 2
        assert stored["last_run_duration_seconds"] == 12.5
        assert stored["last_run_run_id"] == "run-abc"
        assert stored["last_success_at"] is not None
        await repo.release_lock(doc["_id"], "test-worker")
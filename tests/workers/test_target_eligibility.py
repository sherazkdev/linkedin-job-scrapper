from datetime import UTC, datetime, timedelta

import pytest

from app.database.temp_database import open_database
from app.modules.collection.repositories.target_repository import TargetRepository
from app.modules.jobs.models.job import JobSource


@pytest.mark.asyncio
async def test_list_eligible_respects_lock_and_cooldown(integration_db: None) -> None:
    async with open_database("global_jobs_test") as database:
        repo = TargetRepository(database)
        await repo.ensure_defaults()
        acquired = await repo.try_acquire_lock(
            source=JobSource.FIXTURE,
            country_code="DE",
            keyword="backend engineer",
            owner="holder",
            lease_seconds=120,
        )
        assert acquired is not None
        eligible = await repo.list_eligible_targets(allowed_sources=[JobSource.FIXTURE], limit=50)
        keys = {(d["country_code"], d["keyword"]) for d in eligible}
        assert ("DE", "backend engineer") not in keys
        await repo.release_lock(acquired["_id"], "holder")

        future = datetime.now(UTC) + timedelta(hours=1)
        await database["collection_targets"].update_one(
            {"source": "fixture", "country_code": "US", "keyword": "data engineer"},
            {"$set": {"next_eligible_at": future}},
        )
        eligible_after = await repo.list_eligible_targets(
            allowed_sources=[JobSource.FIXTURE],
            limit=50,
        )
        keys_after = {(d["country_code"], d["keyword"]) for d in eligible_after}
        assert ("US", "data engineer") not in keys_after


@pytest.mark.asyncio
async def test_renew_lock_only_matching_owner(integration_db: None) -> None:
    async with open_database("global_jobs_test") as database:
        repo = TargetRepository(database)
        await repo.ensure_defaults()
        doc = await repo.try_acquire_lock(
            source=JobSource.FIXTURE,
            country_code="PK",
            keyword="software engineer",
            owner="worker-a",
            lease_seconds=60,
        )
        assert doc is not None
        renewed = await repo.renew_lock(doc["_id"], owner="worker-a", lease_seconds=120)
        denied = await repo.renew_lock(doc["_id"], owner="worker-b", lease_seconds=120)
        assert renewed is True
        assert denied is False
        await repo.release_lock(doc["_id"], "worker-a")

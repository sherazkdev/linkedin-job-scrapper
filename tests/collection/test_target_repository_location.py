import os

import pytest

from app.core.config import get_settings
from app.database.temp_database import open_database
from app.modules.collection.repositories.target_repository import TargetRepository
from app.modules.jobs.models.job import JobSource


@pytest.mark.asyncio
async def test_target_locks_isolated_by_search_location(integration_db: None) -> None:
    os.environ["ALLOW_COLLECTION_TARGET_INDEX_MIGRATION"] = "true"
    get_settings.cache_clear()
    keyword = "location-lock-pilot-keyword"
    async with open_database("global_jobs_test") as database:
        repo = TargetRepository(database)
        base = {
            "source": JobSource.LINKEDIN,
            "country_code": "PK",
            "keyword": keyword,
        }
        for loc in ("Islamabad, Pakistan", "Rawalpindi, Pakistan"):
            await repo.upsert_target(
                **base,
                search_location=loc,
                enabled=True,
                max_jobs_per_run=1,
            )
        isb = await repo.try_acquire_lock(
            **base,
            search_location="Islamabad, Pakistan",
            owner="test-a",
            lease_seconds=60,
        )
        rwp = await repo.try_acquire_lock(
            **base,
            search_location="Rawalpindi, Pakistan",
            owner="test-b",
            lease_seconds=60,
        )
        assert isb is not None and rwp is not None
        assert isb["_id"] != rwp["_id"]
        await repo.release_lock(isb["_id"], "test-a")
        await repo.release_lock(rwp["_id"], "test-b")
        await database["collection_targets"].delete_many(
            {"source": "linkedin", "keyword": keyword}
        )
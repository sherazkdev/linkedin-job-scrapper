from datetime import UTC, datetime, timedelta

import pytest

from app.core.config import get_settings
from app.database.collection_indexes import COLLECTION_RUNS
from app.database.temp_database import open_database
from app.modules.collection.linkedin.errors import LinkedInCollectionError
from app.modules.collection.models.enums import CollectionRunStatus
from app.modules.scheduling.linkedin_daily_cap import (
    assert_live_linkedin_daily_cap,
    count_live_linkedin_runs_24h,
    linkedin_daily_cap_snapshot,
)
from app.modules.jobs.models.job import JobSource


def _settings(**overrides: object):
    return get_settings().model_copy(
        update={
            "allow_live_linkedin_collection": True,
            "linkedin_max_live_runs_per_24h": 30,
            **overrides,
        }
    )


@pytest.mark.asyncio
async def test_daily_cap_counts_live_runs_only(integration_db: None) -> None:
    async with open_database("global_jobs_test") as database:
        now = datetime.now(UTC)
        before = await count_live_linkedin_runs_24h(database)
        limit = 30
        needed = max(limit - before, 0)
        for i in range(needed):
            await database[COLLECTION_RUNS].insert_one(
                {
                    "run_id": f"cap-run-phase3-{i}",
                    "source": JobSource.LINKEDIN.value,
                    "dry_run": False,
                    "status": CollectionRunStatus.COMPLETED.value,
                    "started_at": now - timedelta(hours=1),
                }
            )
        await database[COLLECTION_RUNS].insert_one(
            {
                "run_id": "old-run-phase3",
                "source": JobSource.LINKEDIN.value,
                "dry_run": False,
                "status": CollectionRunStatus.COMPLETED.value,
                "started_at": now - timedelta(hours=30),
            }
        )
        await database[COLLECTION_RUNS].insert_one(
            {
                "run_id": "dry-run-phase3",
                "source": JobSource.LINKEDIN.value,
                "dry_run": True,
                "status": CollectionRunStatus.COMPLETED.value,
                "started_at": now,
            }
        )
        assert await count_live_linkedin_runs_24h(database) >= limit
        snap = await linkedin_daily_cap_snapshot(database, _settings(linkedin_max_live_runs_per_24h=limit))
        assert snap["blocked"] is True
        assert snap["remaining"] == 0
        with pytest.raises(LinkedInCollectionError):
            await assert_live_linkedin_daily_cap(
                database, _settings(linkedin_max_live_runs_per_24h=limit)
            )


@pytest.mark.asyncio
async def test_daily_cap_ignored_when_live_off(integration_db: None) -> None:
    async with open_database("global_jobs_test") as database:
        now = datetime.now(UTC)
        for i in range(40):
            await database[COLLECTION_RUNS].insert_one(
                {
                    "run_id": f"off-{i}",
                    "source": JobSource.LINKEDIN.value,
                    "dry_run": False,
                    "status": CollectionRunStatus.COMPLETED.value,
                    "started_at": now,
                }
            )
        await assert_live_linkedin_daily_cap(
            database, _settings(allow_live_linkedin_collection=False)
        )
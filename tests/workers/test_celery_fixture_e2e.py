import asyncio
import os

import pytest

from app.core.config import get_settings
from app.database.temp_database import open_database
from app.modules.collection.repositories.target_repository import TargetRepository
from app.modules.jobs.models.job import JobSource
from app.workers.celery_app import celery_app
from app.workers.dispatcher import dispatch_eligible_sync
from app.workers.tasks import run_collection_task


@pytest.fixture
def celery_eager() -> None:
    prev = {
        "task_always_eager": celery_app.conf.task_always_eager,
        "task_eager_propagates": celery_app.conf.task_eager_propagates,
    }
    celery_app.conf.task_always_eager = True
    celery_app.conf.task_eager_propagates = True
    yield
    celery_app.conf.task_always_eager = prev["task_always_eager"]
    celery_app.conf.task_eager_propagates = prev["task_eager_propagates"]


async def _prepare_fixture_targets() -> None:
    async with open_database("global_jobs_test") as database:
        repo = TargetRepository(database)
        await repo.ensure_defaults()
        await repo.upsert_target(
            source=JobSource.LINKEDIN,
            country_code="DE",
            keyword="should-not-run",
            enabled=True,
        )
        for code, kw in (
            ("PK", "software engineer"),
            ("DE", "backend engineer"),
            ("US", "data engineer"),
        ):
            await database["collection_targets"].update_one(
                {"source": "fixture", "country_code": code, "keyword": kw},
                {
                    "$set": {
                        "enabled": True,
                        "next_eligible_at": None,
                        "lock_owner": None,
                        "locked_until": None,
                    }
                },
            )
            await database["jobs"].delete_many({"source": "fixture", "country_code": code})


async def _assert_country_job_counts() -> None:
    async with open_database("global_jobs_test") as database:
        for code in ("PK", "DE", "US"):
            count = await database["jobs"].count_documents(
                {"source": "fixture", "country_code": code}
            )
            assert count >= 2


def test_fixture_countries_via_worker_task(integration_db: None, celery_eager: None) -> None:
    os.environ["CELERY_WORKER_MONGO_DB_NAME"] = "global_jobs_test"
    os.environ["CELERY_TARGET_COOLDOWN_SECONDS"] = "0"
    os.environ["CELERY_DISPATCH_MAX_PER_TICK"] = "10"
    get_settings.cache_clear()
    settings = get_settings()
    assert JobSource.LINKEDIN not in __import__(
        "app.workers.policy", fromlist=["allowed_task_sources"]
    ).allowed_task_sources(settings)

    asyncio.run(_prepare_fixture_targets())

    for code, kw, jobs in (
        ("PK", "software engineer", 2),
        ("DE", "backend engineer", 2),
        ("US", "data engineer", 2),
    ):
        result = run_collection_task.apply(
            kwargs={
                "source": JobSource.FIXTURE.value,
                "country_code": code,
                "keyword": kw,
                "max_jobs": jobs,
            }
        )
        assert result.successful(), result.traceback
        stats = result.result["stats"]
        assert stats["created_count"] >= 1

    asyncio.run(_assert_country_job_counts())

    dispatch = dispatch_eligible_sync()
    assert dispatch["skipped_linkedin"] == 0
    assert dispatch["eligible_count"] >= 1
    assert dispatch["queued_count"] >= 1
    assert all("linkedin" not in key for key in dispatch["queued_keys"])

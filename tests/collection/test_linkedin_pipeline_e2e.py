
import pytest
from tests.fixture_paths import LINKEDIN_FIXTURES as FIXTURES

from app.core.config import get_settings
from app.database.temp_database import open_database
from app.modules.collection.factory import build_collector
from app.modules.collection.repositories.target_repository import TargetRepository
from app.modules.jobs.models.job import JobSource

FIXTURE_JOB_IDS = ["9001001", "9001002"]
def _linkedin_de_backend_query() -> dict:
    return {
        "source": JobSource.LINKEDIN.value,
        "country_code": "DE",
        "keyword": "backend engineer",
    }


TARGET_QUERY = _linkedin_de_backend_query()


async def _reset_linkedin_fixture_state(database) -> None:
    await TargetRepository(database).ensure_defaults()
    await database["jobs"].delete_many(
        {"source": JobSource.LINKEDIN.value, "sourceJobId": {"$in": FIXTURE_JOB_IDS}}
    )
    await database["collection_checkpoints"].delete_many(TARGET_QUERY)
    await database["collection_runs"].delete_many(
        {"source": JobSource.LINKEDIN.value, "country_code": "DE", "keyword": "backend engineer"}
    )
    await database["collection_targets"].update_many(
        TARGET_QUERY,
        {
            "$set": {
                "lock_owner": None,
                "locked_until": None,
                "enabled": True,
                "search_location": "",
            }
        },
    )
    await database["collection_targets"].update_many(
        {**TARGET_QUERY, "search_location": {"$exists": False}},
        {
            "$set": {
                "lock_owner": None,
                "locked_until": None,
                "enabled": True,
                "search_location": "",
            }
        },
    )


@pytest.mark.asyncio
async def test_linkedin_offline_pipeline_persists_jobs(integration_db: None) -> None:
    settings = get_settings()
    db_name = "global_jobs_test"
    async with open_database(db_name) as database:
        await _reset_linkedin_fixture_state(database)
        before = await database["jobs"].count_documents({"source": JobSource.LINKEDIN.value})
        collector = build_collector(
            database,
            settings,
            JobSource.LINKEDIN,
            linkedin_offline_html_root=FIXTURES,
        )
        summary = await collector.collect(
            source=JobSource.LINKEDIN,
            country_code="DE",
            keyword="backend engineer",
            max_jobs=2,
            dry_run=False,
            run_owner="test-linkedin-offline",
        )
        after = await database["jobs"].count_documents({"source": JobSource.LINKEDIN.value})
        assert summary["stats"]["created_count"] == 2
        assert after - before == 2
        await database["collection_checkpoints"].delete_many(TARGET_QUERY)
        dup = await collector.collect(
            source=JobSource.LINKEDIN,
            country_code="DE",
            keyword="backend engineer",
            max_jobs=2,
            dry_run=False,
            run_owner="test-linkedin-dup",
        )
        await collector.shutdown()
        assert dup["stats"]["unchanged_count"] == 2


@pytest.mark.asyncio
async def test_linkedin_dry_run_no_writes(integration_db: None) -> None:
    settings = get_settings()
    async with open_database("global_jobs_test") as database:
        await _reset_linkedin_fixture_state(database)
        jobs_before = await database["jobs"].count_documents({"source": JobSource.LINKEDIN.value})
        runs_before = await database["collection_runs"].count_documents({})
        collector = build_collector(
            database,
            settings,
            JobSource.LINKEDIN,
            linkedin_offline_html_root=FIXTURES,
        )
        await collector.collect(
            source=JobSource.LINKEDIN,
            country_code="DE",
            keyword="backend engineer",
            max_jobs=2,
            dry_run=True,
            run_owner="test-linkedin-dry",
        )
        await collector.shutdown()
        linkedin_jobs = await database["jobs"].count_documents(
            {"source": JobSource.LINKEDIN.value}
        )
        assert jobs_before == linkedin_jobs
        assert runs_before == await database["collection_runs"].count_documents({})

import pytest

from app.core.config import get_settings
from app.database.temp_database import open_database
from app.modules.collection.factory import build_collector
from app.modules.jobs.models.job import JobSource


@pytest.mark.asyncio
async def test_dry_run_writes_nothing(integration_db: None) -> None:
    settings = get_settings()
    db_name = "global_jobs_test"
    async with open_database(db_name) as database:
        jobs_before = await database["jobs"].count_documents({})
        runs_before = await database["collection_runs"].count_documents({})
        collector = build_collector(database, settings, JobSource.FIXTURE)
        await collector.collect(
            source=JobSource.FIXTURE,
            country_code="DE",
            keyword="backend engineer",
            max_jobs=3,
            dry_run=True,
            run_owner="test-dry-run",
        )
        jobs_after = await database["jobs"].count_documents({})
        runs_after = await database["collection_runs"].count_documents({})
    assert jobs_before == jobs_after
    assert runs_before == runs_after


import pytest
from tests.fixture_paths import GREENHOUSE_SAMPLE as FIXTURE

from app.core.config import get_settings
from app.modules.collection.factory import build_collector
from app.modules.jobs.models.job import JobSource


@pytest.mark.asyncio
async def test_scoped_id_second_collect_is_unchanged(
    require_integration: None,
    integration_db: None,
) -> None:
    from app.database.mongodb import get_mongodb

    db = get_mongodb().database
    settings = get_settings()
    await db["collection_checkpoints"].delete_many({"source": JobSource.GREENHOUSE.value})
    await db["jobs"].delete_many(
        {"source": JobSource.GREENHOUSE.value, "sourceJobId": "sample:4011001"}
    )

    collector = build_collector(
        db,
        settings,
        JobSource.GREENHOUSE,
        board_token="sample",
        public_board_offline_fixture=FIXTURE,
    )
    try:
        first = await collector.collect(
            source=JobSource.GREENHOUSE,
            country_code="US",
            keyword="engineer",
            max_jobs=5,
            dry_run=False,
            run_owner="pytest-dedup",
        )
        await db["collection_checkpoints"].delete_many(
            {"source": JobSource.GREENHOUSE.value, "country_code": "US", "keyword": "engineer"}
        )
        second = await collector.collect(
            source=JobSource.GREENHOUSE,
            country_code="US",
            keyword="engineer",
            max_jobs=5,
            dry_run=False,
            run_owner="pytest-dedup",
        )
    finally:
        await collector.shutdown()

    first_writes = first["stats"]["created_count"] + first["stats"]["updated_count"]
    assert first_writes >= 1, first["stats"]
    assert second["stats"]["created_count"] == 0
    assert (
        second["stats"]["unchanged_count"] + second["stats"]["updated_count"]
    ) >= 1, second["stats"]
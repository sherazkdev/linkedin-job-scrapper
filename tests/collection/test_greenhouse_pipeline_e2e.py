
import pytest
from tests.fixture_paths import GREENHOUSE_SAMPLE as FIXTURE

from app.core.config import get_settings
from app.modules.collection.factory import build_collector
from app.modules.jobs.models.job import JobSource


@pytest.mark.asyncio
async def test_greenhouse_offline_collect_persists(
    require_integration: None,
    integration_db: None,
) -> None:
    settings = get_settings()
    from app.database.mongodb import get_mongodb

    database = get_mongodb().database
    marker_id = "sample:4011001"
    await database["jobs"].delete_many(
        {
            "source": JobSource.GREENHOUSE.value,
            "sourceJobId": {"$in": [marker_id, "4011001"]},
        }
    )
    await database["collection_checkpoints"].delete_many(
        {
            "source": JobSource.GREENHOUSE.value,
            "country_code": "US",
            "keyword": "engineer",
        }
    )

    collector = build_collector(
        database,
        settings,
        JobSource.GREENHOUSE,
        board_token="sample",
        public_board_offline_fixture=FIXTURE,
    )
    try:
        summary = await collector.collect(
            source=JobSource.GREENHOUSE,
            country_code="US",
            keyword="engineer",
            max_jobs=5,
            dry_run=False,
            run_owner="pytest-greenhouse",
        )
    finally:
        await collector.shutdown()

    assert summary["stats"]["created_count"] >= 1
    assert summary["adapter_metrics"]["valid_listings"] >= 1

    stored = await database["jobs"].find_one(
        {"source": JobSource.GREENHOUSE.value, "sourceJobId": marker_id}
    )
    assert stored is not None
    assert stored["title"] == "Backend Engineer"
    assert stored["search_country_code"] == "US"
    assert stored["country_code"] == "DE"
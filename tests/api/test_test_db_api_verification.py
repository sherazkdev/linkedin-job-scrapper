"""API reads against the same DB as integration tests (MONGO_DB_NAME=global_jobs_test)."""

from pathlib import Path

import httpx
import pytest

from app.core.config import get_settings
from app.modules.collection.factory import build_collector
from app.modules.jobs.models.job import JobSource

FIXTURE = (
    Path(__file__).resolve().parents[1]
    / "fixtures"
    / "public_boards"
    / "greenhouse"
    / "sample.json"
)


@pytest.mark.asyncio
async def test_collect_then_api_reads_test_db(
    async_client: httpx.AsyncClient,
    require_integration: None,
    integration_db: None,
) -> None:
    """Pytest async_client lifespan uses MONGO_DB_NAME from env (global_jobs_test in CI)."""
    from app.database.mongodb import get_mongodb

    db = get_mongodb().database
    settings = get_settings()
    assert settings.mongo_db_name == "global_jobs_test"

    await db["collection_checkpoints"].delete_many(
        {"source": JobSource.GREENHOUSE.value, "country_code": "US", "keyword": "engineer"}
    )
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
        await collector.collect(
            source=JobSource.GREENHOUSE,
            country_code="US",
            keyword="engineer",
            max_jobs=5,
            dry_run=False,
            run_owner="pytest-api-verify",
        )
    finally:
        await collector.shutdown()

    response = await async_client.get(
        "/api/v1/jobs",
        params={"source": "greenhouse", "q": "Backend", "page_size": 10},
    )
    assert response.status_code == 200
    items = response.json()["data"]["items"]
    assert any(i["source_job_id"] == "sample:4011001" for i in items)

    detail = await async_client.get("/api/v1/jobs/stats")
    assert detail.status_code == 200
    assert "total_active" in detail.json()["data"]
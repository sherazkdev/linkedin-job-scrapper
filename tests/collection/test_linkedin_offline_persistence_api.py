"""Offline: collect LinkedIn fixtures into test DB then read via jobs API (no live browser)."""

from pathlib import Path

import httpx
import pytest
from tests.fixture_paths import LINKEDIN_FIXTURES as FIXTURES

from app.core.config import get_settings
from app.database.temp_database import open_database
from app.main import create_app
from app.modules.collection.factory import build_collector
from app.modules.jobs.models.job import JobSource


@pytest.mark.asyncio
async def test_linkedin_offline_collect_then_api_lists_jobs(integration_db: None) -> None:
    settings = get_settings()
    db_name = settings.mongo_db_name
    async with open_database(db_name) as database:
        await database["jobs"].delete_many(
            {"source": JobSource.LINKEDIN.value, "sourceJobId": {"$in": ["9001001", "9001002"]}}
        )
        await database["collection_checkpoints"].delete_many(
            {"source": JobSource.LINKEDIN.value, "country_code": "DE", "keyword": "backend engineer"}
        )
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
            run_owner="test-offline-api",
        )
        await collector.shutdown()
        assert summary["stats"]["created_count"] == 2

    app = create_app()
    transport = httpx.ASGITransport(app=app)
    async with app.router.lifespan_context(app):
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get(
                "/api/v1/jobs",
                params={"source": "linkedin", "country_code": "DE", "page_size": 10},
            )
            assert response.status_code == 200
            items = response.json()["data"]["items"]
            ids = {item["source_job_id"] for item in items}
            assert "9001001" in ids
            assert "9001002" in ids
            detail = await client.get("/api/v1/jobs/9001001", params={"source": "linkedin"})
            assert detail.status_code == 200
            body = detail.json()["data"]
            assert body["title"]
            assert body["company"]
            assert body.get("data_provenance") in (
                "offline_provider_fixture",
                "synthetic_fixture",
                "unknown",
                "live_api_verified",
            )
            assert Path(body["job_url"]).name or body["job_url"]
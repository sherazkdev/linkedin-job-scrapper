import httpx
import pytest
from httpx import ASGITransport

from app.core.config import get_settings
from app.database.mongodb import get_mongodb
from app.main import create_app
from app.modules.coverage.manifest import load_manifest, validate_manifest
from app.modules.coverage.report import build_coverage_report


@pytest.mark.asyncio
async def test_build_coverage_report_manifest_verified(integration_db: None) -> None:
    data = load_manifest()
    validate_manifest(data)
    mongodb = get_mongodb()
    report = await build_coverage_report(mongodb.database)
    assert report["verdict"]["target_configuration_verified"] is True
    assert report["verdict"]["real_global_data_coverage_verified"] is False
    assert report["required"]["target_combinations"] == 2000
    assert "source_capability_matrix" in report
    assert "job_store_provenance" in report
    assert report["target_layers"]["configured_manifest_combinations"] == 2000


@pytest.mark.asyncio
async def test_internal_coverage_requires_token(
    integration_db: None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("INTERNAL_OPS_TOKEN", "test-token-abc")
    get_settings.cache_clear()
    app = create_app()
    async with app.router.lifespan_context(app):
        transport = ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            ok = await client.get(
                "/internal/v1/monitoring/coverage",
                headers={"X-Internal-Ops-Token": "test-token-abc"},
            )
            assert ok.status_code == 200
            body = ok.json()
            assert body["verdict"]["target_configuration_verified"] is True
            assert body["verdict"]["real_global_data_coverage_verified"] is False
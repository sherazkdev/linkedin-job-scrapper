import json
from pathlib import Path

import pytest

from app.database.collection_indexes import COVERAGE_TARGETS, ensure_coverage_indexes
from app.database.mongodb import get_mongodb
from app.modules.coverage.manifest import iter_canonical_targets, load_manifest, validate_manifest
from app.modules.coverage.repository import CoverageTargetRepository


@pytest.fixture
def mini_manifest(tmp_path: Path) -> Path:
    mini = {
        "schema_version": 1,
        "counts": {"countries": 2, "keywords": 2, "canonical_target_pairs": 4},
        "countries": [
            {"name": "Pakistan", "country_code": "PK"},
            {"name": "United Arab Emirates", "country_code": "AE"},
        ],
        "keywords": ["Software Engineer", "Data Analyst"],
        "targets": [
            {"country_code": "PK", "keyword": "Software Engineer"},
            {"country_code": "PK", "keyword": "Data Analyst"},
            {"country_code": "AE", "keyword": "Software Engineer"},
            {"country_code": "AE", "keyword": "Data Analyst"},
        ],
    }
    path = tmp_path / "mini_coverage.json"
    path.write_text(json.dumps(mini), encoding="utf-8")
    return path


@pytest.mark.asyncio
async def test_coverage_import_dry_run_then_idempotent(
    integration_db: None,
    mini_manifest: Path,
) -> None:
    data = load_manifest(mini_manifest)
    meta = validate_manifest(data)
    rows = iter_canonical_targets(data)
    mongodb = get_mongodb()
    database = mongodb.database
    await ensure_coverage_indexes(database)
    await database[COVERAGE_TARGETS].delete_many({})
    repo = CoverageTargetRepository(database)

    dry = await repo.import_targets(rows, schema_version=meta["schema_version"], apply=False)
    assert dry["scanned"] == 4
    assert dry["would_insert"] == 4
    assert await repo.count_all() == 0

    first = await repo.import_targets(rows, schema_version=meta["schema_version"], apply=True)
    assert first["inserted"] == 4
    assert await repo.count_all() == 4
    assert await repo.count_enabled() == 0

    sample = await database[COVERAGE_TARGETS].find_one({"country_code": "PK"})
    assert sample is not None
    assert sample["enabled"] is False
    assert sample["collection_status"] == "awaiting_approved_source"

    second = await repo.import_targets(rows, schema_version=meta["schema_version"], apply=True)
    assert second["inserted"] == 0
    assert second["updated_metadata"] == 4
    assert await repo.count_all() == 4
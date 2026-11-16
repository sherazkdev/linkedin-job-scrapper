from pathlib import Path

import pytest

from app.modules.coverage.manifest import (
    ManifestValidationError,
    default_manifest_path,
    load_manifest,
    slug_keyword,
    target_id,
    validate_manifest,
)


def test_default_manifest_path_exists() -> None:
    path = default_manifest_path()
    assert path.is_file(), f"missing manifest at {path}"


def test_canonical_manifest_counts() -> None:
    data = load_manifest()
    meta = validate_manifest(data)
    assert meta["countries"] == 40
    assert meta["keywords"] == 50
    assert meta["targets"] == 2000
    assert data["counts"]["canonical_target_pairs"] == 2000


def test_target_id_deterministic() -> None:
    assert target_id("DE", "Software Engineer") == "DE:software-engineer"
    assert slug_keyword("Product Manager (IT)") == "product-manager-it"


def test_reject_invalid_country_code() -> None:
    data = load_manifest()
    broken = {**data, "countries": [{"name": "Bad", "country_code": "GER"}] + data["countries"][1:]}
    with pytest.raises(ManifestValidationError):
        validate_manifest(broken)


def test_mini_fixture_manifest(tmp_path: Path) -> None:
    mini = {
        "schema_version": 1,
        "counts": {"countries": 2, "keywords": 2, "canonical_target_pairs": 4},
        "countries": [
            {"name": "Pakistan", "country_code": "PK"},
            {"name": "Germany", "country_code": "DE"},
        ],
        "keywords": ["Software Engineer", "Data Scientist"],
        "targets": [
            {"country_code": "PK", "keyword": "Software Engineer"},
            {"country_code": "PK", "keyword": "Data Scientist"},
            {"country_code": "DE", "keyword": "Software Engineer"},
            {"country_code": "DE", "keyword": "Data Scientist"},
        ],
    }
    path = tmp_path / "mini.json"
    path.write_text(__import__("json").dumps(mini), encoding="utf-8")
    loaded = load_manifest(path)
    meta = validate_manifest(loaded)
    assert meta["countries"] == 2
    assert meta["targets"] == 4
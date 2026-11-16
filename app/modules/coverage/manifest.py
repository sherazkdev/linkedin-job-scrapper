import json
import re
from pathlib import Path
from typing import Any

MANIFEST_FILENAME = "global_jobs_40_countries_50_keywords_manifest.json"


def default_manifest_path() -> Path:
    return Path(__file__).resolve().parents[3] / "config" / MANIFEST_FILENAME


def slug_keyword(keyword: str) -> str:
    value = keyword.strip().lower()
    value = re.sub(r"[^a-z0-9]+", "-", value)
    return value.strip("-") or "keyword"


def target_id(country_code: str, keyword: str) -> str:
    return f"{country_code.upper()}:{slug_keyword(keyword)}"


class ManifestValidationError(ValueError):
    pass


def load_manifest(path: Path | None = None) -> dict[str, Any]:
    manifest_path = path or default_manifest_path()
    if not manifest_path.is_file():
        raise FileNotFoundError(f"Coverage manifest not found: {manifest_path}")
    with manifest_path.open(encoding="utf-8") as handle:
        return json.load(handle)


def validate_manifest(data: dict[str, Any]) -> dict[str, Any]:
    countries = data.get("countries")
    keywords = data.get("keywords")
    targets = data.get("targets")
    if (
        not isinstance(countries, list)
        or not isinstance(keywords, list)
        or not isinstance(targets, list)
    ):
        raise ManifestValidationError(
            "manifest must include countries, keywords, and targets arrays"
        )

    counts_meta = data.get("counts") if isinstance(data.get("counts"), dict) else {}
    expected_countries = int(counts_meta.get("countries", 40))
    expected_keywords = int(counts_meta.get("keywords", 50))
    expected_targets = int(
        counts_meta.get("canonical_target_pairs", counts_meta.get("targets", 2000))
    )

    country_codes = {str(c["country_code"]).upper() for c in countries if isinstance(c, dict)}
    if len(country_codes) != expected_countries:
        raise ManifestValidationError(
            f"expected {expected_countries} countries, got {len(country_codes)}"
        )
    for code in country_codes:
        if len(code) != 2 or not code.isalpha():
            raise ManifestValidationError(f"invalid ISO country code: {code}")

    keyword_set = {str(k).strip() for k in keywords}
    if len(keyword_set) != expected_keywords:
        raise ManifestValidationError(
            f"expected {expected_keywords} keywords, got {len(keyword_set)}"
        )

    pairs: set[tuple[str, str]] = set()
    for row in targets:
        if not isinstance(row, dict):
            continue
        cc = str(row["country_code"]).upper()
        kw = str(row["keyword"]).strip()
        if cc not in country_codes:
            raise ManifestValidationError(f"target country not in manifest list: {cc}")
        if kw not in keyword_set:
            raise ManifestValidationError(f"target keyword not in manifest list: {kw}")
        pair = (cc, kw.lower())
        if pair in pairs:
            raise ManifestValidationError(f"duplicate target: {cc} / {kw}")
        pairs.add(pair)

    if len(pairs) != expected_targets:
        raise ManifestValidationError(
            f"expected {expected_targets} unique targets, got {len(pairs)}"
        )

    name_by_code = {
        str(c["country_code"]).upper(): str(c.get("name", c["country_code"]))
        for c in countries
        if isinstance(c, dict)
    }
    return {
        "countries": len(country_codes),
        "keywords": len(keyword_set),
        "targets": len(pairs),
        "name_by_code": name_by_code,
        "schema_version": data.get("schema_version", 1),
    }


def iter_canonical_targets(data: dict[str, Any]) -> list[dict[str, str]]:
    meta = validate_manifest(data)
    name_by_code = meta["name_by_code"]
    rows: list[dict[str, str]] = []
    for row in data["targets"]:
        cc = str(row["country_code"]).upper()
        kw = str(row["keyword"]).strip()
        rows.append(
            {
                "target_id": target_id(cc, kw),
                "country_code": cc,
                "country_name": name_by_code.get(cc, cc),
                "keyword": kw.lower(),
                "keyword_display": kw,
            }
        )
    return rows
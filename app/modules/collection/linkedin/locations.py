"""LinkedIn search location labels from the canonical 40-country manifest."""

from functools import lru_cache

from app.modules.coverage.manifest import load_manifest, validate_manifest


@lru_cache(maxsize=1)
def _name_by_iso() -> dict[str, str]:
    data = load_manifest()
    validate_manifest(data)
    return {
        str(row["country_code"]).upper(): str(row["name"])
        for row in data["countries"]
        if isinstance(row, dict)
    }


def linkedin_search_location(country_code: str) -> str:
    """Map ISO code to LinkedIn `location` query (legacy scraper country names)."""
    code = country_code.upper()
    return _name_by_iso().get(code, code)
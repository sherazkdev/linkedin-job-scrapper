"""Match job cards to an explicit LinkedIn search location (city-level when specified)."""

from app.modules.collection.linkedin.locations import linkedin_search_location


def resolve_search_location(country_code: str, override: str | None) -> str:
    if override and override.strip():
        return override.strip()
    return linkedin_search_location(country_code)


def job_matches_search_location(location_text: str | None, search_location: str) -> bool:
    """Require primary city to match when search_location names a city (before the first comma)."""
    if not location_text or not location_text.strip():
        return False
    required_primary = search_location.split(",")[0].strip().lower()
    if not required_primary:
        return True
    primary = location_text.split(",")[0].strip().lower()
    if required_primary == "islamabad":
        if primary in {"rawalpindi", "lahore", "karachi", "faisalabad", "multan", "peshawar"}:
            return False
        return primary == "islamabad"
    return required_primary in primary or primary == required_primary
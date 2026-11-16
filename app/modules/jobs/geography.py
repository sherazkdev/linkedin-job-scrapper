"""Lightweight job location resolution (no external geo services)."""

import re
from dataclasses import dataclass

# ISO alpha-2 codes keyed by normalized tokens (country names, common cities).
_TOKEN_TO_COUNTRY: dict[str, str] = {
    "pakistan": "PK",
    "karachi": "PK",
    "lahore": "PK",
    "islamabad": "PK",
    "germany": "DE",
    "berlin": "DE",
    "munich": "DE",
    "frankfurt": "DE",
    "united states": "US",
    "usa": "US",
    "u.s.": "US",
    "austin": "US",
    "new york": "US",
    "san francisco": "US",
    "united kingdom": "GB",
    "uk": "GB",
    "england": "GB",
    "london": "GB",
    "manchester": "GB",
    "uae": "AE",
    "united arab emirates": "AE",
    "dubai": "AE",
    "abu dhabi": "AE",
    "sweden": "SE",
    "stockholm": "SE",
    "canada": "CA",
    "toronto": "CA",
    "netherlands": "NL",
    "amsterdam": "NL",
    "france": "FR",
    "paris": "FR",
}


@dataclass(frozen=True, slots=True)
class GeographyResolution:
    search_country_code: str
    country_code: str | None
    location_text: str | None
    city: str | None
    region: str | None
    is_remote: bool | None


def normalize_search_country(code: str) -> str:
    normalized = code.strip().upper()
    if len(normalized) != 2 or not normalized.isalpha():
        raise ValueError("search_country_code must be ISO 3166-1 alpha-2")
    return normalized


def resolve_geography(
    *,
    search_country_code: str,
    location_text: str | None,
    city: str | None = None,
    workplace_type: str | None = None,
) -> GeographyResolution:
    """Resolve actual job country from displayed location; never assume search == job country."""
    search = normalize_search_country(search_country_code)
    location = (location_text or "").strip() or None
    city_clean = city.strip() if city else None

    remote_flag = _detect_remote(location, workplace_type)

    if not location and not city_clean:
        return GeographyResolution(
            search_country_code=search,
            country_code=None,
            location_text=None,
            city=city_clean,
            region=None,
            is_remote=remote_flag,
        )

    if remote_flag is True and not _location_has_country_hint(location, city_clean):
        return GeographyResolution(
            search_country_code=search,
            country_code=None,
            location_text=location,
            city=city_clean,
            region=None,
            is_remote=True,
        )

    resolved = _resolve_country_from_text(location, city_clean)
    region = _parse_region(location, city_clean)

    return GeographyResolution(
        search_country_code=search,
        country_code=resolved,
        location_text=location,
        city=city_clean or _parse_city(location),
        region=region,
        is_remote=remote_flag,
    )


def _detect_remote(location: str | None, workplace_type: str | None) -> bool | None:
    if workplace_type:
        key = workplace_type.strip().lower()
        if key == "remote":
            return True
        if key in {"on_site", "hybrid"}:
            return False if not (location and "remote" in location.lower()) else None
    if not location:
        return None
    lowered = location.lower()
    if re.search(r"\bremote\b", lowered) and not _location_has_country_hint(location, None):
        return True
    return None


def _location_has_country_hint(location: str | None, city: str | None) -> bool:
    return _resolve_country_from_text(location, city) is not None


def _resolve_country_from_text(location: str | None, city: str | None) -> str | None:
    candidates: list[str] = []
    if location:
        candidates.extend(part.strip().lower() for part in location.split(","))
        candidates.append(location.strip().lower())
    if city:
        candidates.append(city.strip().lower())
    for token in reversed(candidates):
        if not token:
            continue
        if token in _TOKEN_TO_COUNTRY:
            return _TOKEN_TO_COUNTRY[token]
        for key, code in _TOKEN_TO_COUNTRY.items():
            if key in token or token in key:
                return code
    return None


def _parse_city(location: str | None) -> str | None:
    if not location:
        return None
    return location.split(",")[0].strip() or None


def _parse_region(location: str | None, city: str | None) -> str | None:
    if not location:
        return None
    parts = [p.strip() for p in location.split(",") if p.strip()]
    if len(parts) >= 3:
        return parts[1]
    if len(parts) == 2 and city and parts[0].lower() == city.lower():
        return None
    return None
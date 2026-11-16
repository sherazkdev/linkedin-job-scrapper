"""Documented market-search provider feasibility per canonical country (research only)."""

from enum import StrEnum
from typing import Any

from app.modules.coverage.manifest import load_manifest, validate_manifest


class ProviderSupport(StrEnum):
    VERIFIED = "verified_documentation"
    UNKNOWN = "unknown_needs_operator_verification"
    UNSUPPORTED = "unsupported_per_public_docs"


# Adzuna job API country path slugs (developer.adzuna.com; ~16–19 markets).
ADZUNA_COUNTRY: dict[str, str] = {
    "AU": "au",
    "AT": "at",
    "BE": "be",
    "BR": "br",
    "CA": "ca",
    "CH": "ch",
    "DE": "de",
    "ES": "es",
    "FR": "fr",
    "GB": "gb",
    "IN": "in",
    "IT": "it",
    "MX": "mx",
    "NL": "nl",
    "NZ": "nz",
    "PL": "pl",
    "SG": "sg",
    "US": "us",
    "ZA": "za",
}

# Careerjet locale_code values (careerjet API v4 / client locale tables).
CAREERJET_LOCALE: dict[str, str] = {
    "AE": "en_AE",
    "AU": "en_AU",
    "CA": "en_CA",
    "CH": "de_CH",
    "CN": "en_CN",
    "CZ": "cs_CZ",
    "DE": "de_DE",
    "DK": "da_DK",
    "FI": "fi_FI",
    "FR": "fr_FR",
    "GB": "en_GB",
    "HK": "en_HK",
    "IE": "en_IE",
    "IN": "en_IN",
    "IT": "it_IT",
    "JP": "ja_JP",
    "KW": "en_KW",
    "MY": "en_MY",
    "NL": "nl_NL",
    "NZ": "en_NZ",
    "OM": "en_OM",
    "PH": "en_PH",
    "PK": "en_PK",
    "PL": "pl_PL",
    "QA": "en_QA",
    "SA": "en_SA",
    "SG": "en_SG",
    "TH": "en_TH",
    "US": "en_US",
    "VN": "en_VN",
    "ZA": "en_ZA",
    "ES": "es_ES",
    "MX": "es_MX",
    "SE": "sv_SE",
    "NO": "no_NO",
    "TR": "tr_TR",
    "KR": "ko_KR",
}

# Jooble REST — per-country portal (help.jooble.org); not all manifest countries documented.
JOOBLE_PORTAL: dict[str, str] = {
    "PK": "pk",
    "AE": "ae",
    "US": "us",
    "GB": "uk",
    "DE": "de",
    "FR": "fr",
    "NL": "nl",
    "PL": "pl",
    "CZ": "cz",
    "IN": "in",
    "AU": "au",
    "CA": "ca",
    "SG": "sg",
    "MY": "my",
    "PH": "ph",
    "ZA": "za",
    "NG": "ng",
    "BR": "br",
    "MX": "mx",
    "JP": "jp",
    "KR": "kr",
    "SE": "se",
    "CH": "ch",
    "AT": "at",
    "ES": "es",
    "IT": "it",
    "TH": "th",
    "VN": "vn",
    "ID": "id",
    "TR": "tr",
}


def _provider_entry(
    slug: str,
    country_code: str,
    mapping: dict[str, str],
    *,
    extra_verified: set[str] | None = None,
) -> dict[str, str]:
    key = country_code.upper()
    if key in mapping:
        status = ProviderSupport.VERIFIED
        note = f"locale/path={mapping[key]}"
    elif extra_verified and key in extra_verified:
        status = ProviderSupport.UNKNOWN
        note = "listed in secondary sources; confirm with publisher"
    else:
        status = ProviderSupport.UNSUPPORTED
        note = "not in documented country list"
    return {"provider": slug, "support": status.value, "detail": note}


def build_country_capability_matrix() -> list[dict[str, Any]]:
    manifest = load_manifest()
    validate_manifest(manifest)
    rows: list[dict[str, Any]] = []
    countries_with_any_verified = 0
    for country in manifest["countries"]:
        code = str(country["country_code"]).upper()
        name = str(country["name"])
        providers = [
            _provider_entry("adzuna", code, ADZUNA_COUNTRY),
            _provider_entry("careerjet", code, CAREERJET_LOCALE, extra_verified={"EG", "BH"}),
            _provider_entry("jooble", code, JOOBLE_PORTAL),
        ]
        verified = [p for p in providers if p["support"] == ProviderSupport.VERIFIED.value]
        if verified:
            countries_with_any_verified += 1
        primary = verified[0]["provider"] if verified else None
        if primary == "adzuna":
            fallback = next((p["provider"] for p in verified if p["provider"] != "adzuna"), None)
        elif primary:
            adzuna_ok = any(
                p["provider"] == "adzuna" and p["support"] == ProviderSupport.VERIFIED.value
                for p in providers
            )
            fallback = "adzuna" if adzuna_ok else None
        else:
            fallback = None
        blockers: list[str] = []
        if not verified:
            blockers.append("no_documented_market_search_api")
        blockers.append("api_credentials_not_configured")
        blockers.append("commercial_redistribution_not_approved")
        rows.append(
            {
                "iso_code": code,
                "country_name": name,
                "candidate_providers": providers,
                "verified_market_search_providers": [p["provider"] for p in verified],
                "recommended_primary": primary,
                "recommended_fallback": fallback,
                "api_credentials_required": True,
                "usage_quota_notes": {
                    "adzuna": "app_id/app_key; rate limits per developer portal",
                    "jooble": "free tier ~100 req/day/key/country (help.jooble.org)",
                    "careerjet": "publisher affiliate key; user_ip/user_agent required",
                },
                "redistribution": "review_each_provider_terms_before_public_api",
                "blockers": blockers,
            }
        )
    return rows


def matrix_summary() -> dict[str, Any]:
    matrix = build_country_capability_matrix()
    with_verified = sum(1 for r in matrix if r["verified_market_search_providers"])
    adzuna_primary = sum(1 for r in matrix if r["recommended_primary"] == "adzuna")
    return {
        "countries_in_manifest": len(matrix),
        "countries_with_any_verified_provider": with_verified,
        "countries_with_adzuna_verified": sum(
            1 for r in matrix if "adzuna" in r["verified_market_search_providers"]
        ),
        "recommended_primary_adzuna_countries": adzuna_primary,
        "notes": (
            "Verification is documentation-level only; no live API calls were made in Phase 3E."
        ),
    }
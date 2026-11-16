"""Source capability matrix (configuration vs verified live acquisition)."""

from enum import StrEnum

from app.modules.jobs.models.job import JobSource


class CollectionMode(StrEnum):
    MARKET_KEYWORD_SEARCH = "market_keyword_search"
    EMPLOYER_BOARD = "employer_board"
    OFFLINE_FIXTURE = "offline_fixture"
    DISABLED = "disabled"


SOURCE_CAPABILITIES: dict[JobSource, dict[str, object]] = {
    JobSource.FIXTURE: {
        "mode": CollectionMode.OFFLINE_FIXTURE,
        "global_country_keyword_search": True,
        "geographic_filtering": "simulated",
        "live_network_default": False,
        "celery_scheduled": True,
        "redistribution_review_required": False,
        "verified_live_data": False,
        "notes": "Fictional pipeline verification only.",
    },
    JobSource.GREENHOUSE: {
        "mode": CollectionMode.EMPLOYER_BOARD,
        "global_country_keyword_search": False,
        "geographic_filtering": "client_keyword_filter_on_board_list",
        "live_network_default": False,
        "celery_scheduled": False,
        "redistribution_review_required": True,
        "verified_live_data": True,
        "notes": "Per-board token; not nationwide search.",
    },
    JobSource.LEVER: {
        "mode": CollectionMode.EMPLOYER_BOARD,
        "global_country_keyword_search": False,
        "geographic_filtering": "limited_api_filters",
        "live_network_default": False,
        "celery_scheduled": False,
        "redistribution_review_required": True,
        "verified_live_data": False,
        "notes": "Site slug required; no global market coverage.",
    },
    JobSource.ASHBY: {
        "mode": CollectionMode.EMPLOYER_BOARD,
        "global_country_keyword_search": False,
        "geographic_filtering": "board_list_only",
        "live_network_default": False,
        "celery_scheduled": False,
        "redistribution_review_required": True,
        "verified_live_data": False,
        "notes": "Job board name required.",
    },
    JobSource.ADZUNA: {
        "mode": CollectionMode.MARKET_KEYWORD_SEARCH,
        "global_country_keyword_search": False,
        "geographic_filtering": "adzuna_country_path_slug",
        "live_network_default": False,
        "celery_scheduled": False,
        "redistribution_review_required": True,
        "verified_live_data": False,
        "notes": "19 manifest countries per docs; credentials required; CLI-only.",
    },
    JobSource.LINKEDIN: {
        "mode": CollectionMode.MARKET_KEYWORD_SEARCH,
        "global_country_keyword_search": True,
        "geographic_filtering": "search_market_parameter",
        "live_network_default": False,
        "celery_scheduled": False,
        "redistribution_review_required": True,
        "verified_live_data": False,
        "notes": "Offline fixtures only; live disabled.",
    },
    JobSource.DEMO: {
        "mode": CollectionMode.DISABLED,
        "global_country_keyword_search": False,
        "geographic_filtering": None,
        "live_network_default": False,
        "celery_scheduled": False,
        "redistribution_review_required": False,
        "verified_live_data": False,
        "notes": "Seed CLI only.",
    },
}


def capability_matrix() -> dict[str, dict[str, object]]:
    return {source.value: dict(meta) for source, meta in SOURCE_CAPABILITIES.items()}
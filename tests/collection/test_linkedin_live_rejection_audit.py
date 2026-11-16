"""Sanitized audit of live pilot rejections (titles/locations only — no PII from sessions)."""

from app.modules.collection.linkedin.keyword_relevance import title_matches_keyword
from app.modules.collection.linkedin.location_filter import job_matches_search_location

# Evidence from Contabo run d76bf755 (keyword: junior erp consultant, location: islamabad, pakistan).
LIVE_KEYWORD = "junior erp consultant"
LIVE_SEARCH_LOCATION = "islamabad, pakistan"


def test_live_card_specialist_transaction_processing_location_rejected() -> None:
    """Job id 4490283952 — detail location was not Islamabad primary (live: location_mismatch)."""
    title = "Specialist, Transaction Processing"
    location = "Karachi, Sindh, Pakistan"
    assert not job_matches_search_location(location, LIVE_SEARCH_LOCATION)
    assert not title_matches_keyword(title, LIVE_KEYWORD)


def test_live_card_integration_engineer_keyword_rejected() -> None:
    """Job id 4490280832 — title lacks junior, erp, and consultant tokens."""
    title = "Integration Engineer"
    location = "Islamabad, Pakistan"
    assert not title_matches_keyword(title, LIVE_KEYWORD)
    assert job_matches_search_location(location, LIVE_SEARCH_LOCATION)


def test_live_card_remote_crossover_location_rejected() -> None:
    """Job id 4488657237 — remote USD listing; primary location not Islamabad."""
    title = "Integration Engineer"
    location = "Remote"
    assert not title_matches_keyword(title, LIVE_KEYWORD)
    assert not job_matches_search_location(location, LIVE_SEARCH_LOCATION)


def test_software_engineer_keyword_matches_typical_title() -> None:
    keyword = "software engineer"
    assert title_matches_keyword("Software Engineer", keyword)
    assert title_matches_keyword("Senior Software Engineer", keyword)
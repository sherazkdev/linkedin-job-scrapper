"""LinkedIn checkpoint fresh-start policy."""

from app.modules.collection.linkedin.checkpoint_policy import (
    persist_linkedin_run_checkpoint,
    prepare_linkedin_run_checkpoint,
)
from app.modules.collection.linkedin.adapter import _build_search_url
from app.modules.collection.linkedin.pagination import LINKEDIN_SEARCH_PAGE_SIZE


def test_prepare_resets_stale_page_index_keeps_processed_ids() -> None:
    stored = {"page_index": 8, "processed_ids": ["123", "456"], "keyword": "software engineer"}
    prepared = prepare_linkedin_run_checkpoint(stored, ignore_stored=False)
    assert prepared is not None
    assert prepared["page_index"] == 0
    assert prepared["processed_ids"] == ["123", "456"]


def test_prepare_ignore_clears_checkpoint() -> None:
    stored = {"page_index": 8, "processed_ids": ["123"]}
    assert prepare_linkedin_run_checkpoint(stored, ignore_stored=True) is None


def test_persist_never_advance_page_index() -> None:
    adapter_ck = {"page_index": 9, "processed_ids": ["a", "b"], "keyword": "se"}
    saved = persist_linkedin_run_checkpoint(adapter_ck)
    assert saved["page_index"] == 0
    assert saved["processed_ids"] == ["a", "b"]


def test_stale_offset_would_skip_newest_without_policy() -> None:
    """Document regression: page_index 8 => start=200 on LinkedIn SERP."""
    start = 8 * LINKEDIN_SEARCH_PAGE_SIZE
    url = _build_search_url(keyword="software engineer", location="Pakistan", start=start, past_24h=True)
    assert "start=200" in url
    prepared = prepare_linkedin_run_checkpoint({"page_index": 8, "processed_ids": []}, ignore_stored=False)
    assert prepared is not None
    fresh_start = prepared["page_index"] * LINKEDIN_SEARCH_PAGE_SIZE
    url_fresh = _build_search_url(
        keyword="software engineer", location="Pakistan", start=fresh_start, past_24h=True
    )
    assert "start=0" in url_fresh


def test_pilot_serp_rejection_titles_from_evidence() -> None:
    """Sanitized titles from 2026-11-23 pilot — filter should reject non-matching, accept SE roles."""
    from app.modules.collection.linkedin.keyword_relevance import title_matches_keyword

    keyword = "software engineer"
    assert title_matches_keyword("Senior Software Developer", keyword)
    assert title_matches_keyword("Principal Software Engineer - Gitlab Java", keyword)
    assert title_matches_keyword("Software Engineer (Contractual)", keyword)
    assert not title_matches_keyword("Mobile Development Engineer", keyword)
    assert not title_matches_keyword("Java Engineer - Spring Boot & Kafka", keyword)
    assert not title_matches_keyword("DevOps Internship", keyword)
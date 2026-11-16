from app.modules.collection.linkedin.keyword_relevance import (
    significant_keyword_tokens,
    title_matches_keyword,
)


def test_wildcard_keyword_passes_all_titles() -> None:
    assert title_matches_keyword("Billing Specialist", "*")
    assert title_matches_keyword(None, "*")


def test_significant_tokens_excludes_short_parts() -> None:
    assert significant_keyword_tokens("AI PM") == []
    assert title_matches_keyword("Product Manager", "AI PM")


def test_junior_erp_consultant_requires_all_tokens() -> None:
    keyword = "Junior ERP Consultant"
    assert title_matches_keyword("Junior ERP Consultant", keyword)
    assert not title_matches_keyword("Billing Specialist", keyword)
    assert not title_matches_keyword("Senior ERP Analyst", keyword)


def test_title_match_is_case_insensitive() -> None:
    assert title_matches_keyword("JUNIOR erp CONSULTANT", "Junior ERP Consultant")


def test_plural_token_variant_matches_singular_keyword() -> None:
    assert title_matches_keyword("Solutions Architect", "solution architect")
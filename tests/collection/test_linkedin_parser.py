from datetime import UTC, datetime

import pytest
from tests.fixture_paths import LINKEDIN_FIXTURES as FIXTURES

from app.modules.collection.linkedin.errors import LinkedInCollectionError, LinkedInFailureState
from app.modules.collection.linkedin.parser import (
    detect_page_state,
    parse_job_detail_html,
    parse_search_job_cards,
    search_page_diagnostics,
)
from app.modules.collection.linkedin.search_page_capture import (
    classify_search_page,
    redact_url_for_log,
)


def test_parse_search_cards_from_fixture() -> None:
    html = (FIXTURES / "search_page_1.html").read_text(encoding="utf-8")
    cards = parse_search_job_cards(html, search_country_code="DE")
    assert len(cards) == 2
    assert cards[0]["source_job_id"] == "9001001"
    assert cards[0]["search_country_code"] == "DE"


def test_parse_job_detail_requires_description() -> None:
    html = (FIXTURES / "job_detail_9001001.html").read_text(encoding="utf-8")
    from app.modules.collection.services.normalizer import JobNormalizer
    from app.modules.jobs.models.job import JobSource

    card = parse_search_job_cards(
        (FIXTURES / "search_page_1.html").read_text(encoding="utf-8"),
        search_country_code="DE",
    )[0]
    raw = parse_job_detail_html(html, card=card)
    job = JobNormalizer(JobSource.LINKEDIN).normalize(raw)
    assert "Northwind" in job.description
    assert job.search_country_code == "DE"
    assert job.country_code == "DE"
    assert job.posted_at.tzinfo is not None


def test_relative_posting_parsing() -> None:
    html = (FIXTURES / "job_detail_9001001.html").read_text(encoding="utf-8")
    search_html = (FIXTURES / "search_page_1.html").read_text(encoding="utf-8")
    card = parse_search_job_cards(search_html, search_country_code="DE")[0]
    card["posted_hint"] = None
    card["posted_text"] = "3 days ago"
    job = parse_job_detail_html(html, card=card)
    assert job.posted_at < datetime.now(UTC)


@pytest.mark.parametrize(
    "file,state",
    [
        ("verification_required.html", LinkedInFailureState.VERIFICATION_REQUIRED),
        ("session_expired.html", LinkedInFailureState.SESSION_EXPIRED),
    ],
)
def test_detect_restriction_pages(file: str, state: LinkedInFailureState) -> None:
    html = (FIXTURES / file).read_text(encoding="utf-8")
    assert detect_page_state(html) == state


@pytest.mark.parametrize(
    "html",
    [
        (
            '<html><body><script>"next":"https://www.linkedin.com/checkpoint/lg/login"</script>'
            '<li class="jobs-search-results__list-item"><div class="base-card">'
            '<a class="base-card__full-link" href="/jobs/view/123">'
            '<h3 class="base-search-card__title">Eng</h3><h4 class="base-search-card__subtitle">Co</h4>'
            "</a></div></li></body></html>"
        ),
        (
            '<html><body><li class="jobs-search-results__list-item"><div class="base-card">'
            '<a class="base-card__full-link" href="/jobs/view/123">'
            '<h3 class="base-search-card__title">Analyst</h3><h4 class="base-search-card__subtitle">Co</h4>'
            "<span>Role requires security verification clearance</span>"
            "</a></div></li></body></html>"
        ),
    ],
)
def test_detect_page_state_ignores_verification_noise_on_jobs_html(html: str) -> None:
    assert detect_page_state(html) is None
    cards = parse_search_job_cards(html, search_country_code="US")
    assert len(cards) == 1


def test_checkpoint_challenge_in_bundle_with_jobs_allows_parse() -> None:
    """SPA bundles may embed challenge URLs while still rendering results."""
    html = (
        '<html><body><script>"/checkpoint/challenge/"</script>'
        '<li class="jobs-search-results__list-item"><div class="base-card">'
        '<a href="/jobs/view/1"><h3 class="base-search-card__title">T</h3>'
        '<h4 class="base-search-card__subtitle">C</h4></a></div></li></body></html>'
    )
    assert detect_page_state(html) is None
    assert len(parse_search_job_cards(html, search_country_code="US")) == 1


def test_missing_required_selectors_fail_loudly() -> None:
    with pytest.raises(LinkedInCollectionError) as err:
        parse_search_job_cards(
            "<html><body><div class='base-card'></div></body></html>",
            search_country_code="US",
        )
    assert err.value.state == LinkedInFailureState.UNSUPPORTED_PAGE_STRUCTURE


def test_parse_job_search_card_layout() -> None:
    html = (FIXTURES / "search_page_job_search_card.html").read_text(encoding="utf-8")
    cards = parse_search_job_cards(html, search_country_code="PK")
    assert len(cards) == 1
    assert cards[0]["source_job_id"] == "9102001"
    assert cards[0]["location_text"] == "Islamabad, Pakistan"


def test_genuine_empty_returns_no_cards_without_unsupported() -> None:
    html = (FIXTURES / "search_page_genuine_empty.html").read_text(encoding="utf-8")
    assert search_page_diagnostics(html)["genuine_empty"] is True
    assert parse_search_job_cards(html, search_country_code="PK") == []


def test_parse_slug_job_url() -> None:
    html = """
    <html><body>
      <div class="base-card" data-entity-urn="urn:li:jobPosting:5551001">
        <a class="base-card__full-link"
           href="https://www.linkedin.com/jobs/view/software-engineer-5551001?trk=public">
          <h3 class="base-search-card__title">Software Engineer</h3>
          <h4 class="base-search-card__subtitle">Example Co</h4>
          <span class="job-search-card__location">Islamabad, Pakistan</span>
        </a>
      </div>
    </body></html>
    """
    cards = parse_search_job_cards(html, search_country_code="PK")
    assert len(cards) == 1
    assert cards[0]["source_job_id"] == "5551001"


def test_spa_shell_raises_unsupported_not_empty_list() -> None:
    with pytest.raises(LinkedInCollectionError) as err:
        parse_search_job_cards("<html><body><div id='app'></div></body></html>", search_country_code="PK")
    assert err.value.state == LinkedInFailureState.UNSUPPORTED_PAGE_STRUCTURE


def test_redact_url_strips_sensitive_query_params() -> None:
    raw = (
        "https://www.linkedin.com/jobs/search/?keywords=Engineer&location=PK"
        "&session_redirect=[secret]&trk=ABCDE"
    )
    redacted = redact_url_for_log(raw)
    assert "keywords=Engineer" in redacted
    assert "location=PK" in redacted
    assert "secret" not in redacted
    assert "ABCDE" not in redacted


@pytest.mark.parametrize(
    "fixture,expected",
    [
        ("search_page_1.html", "jobs"),
        ("search_page_genuine_empty.html", "empty"),
        ("verification_required.html", "verification"),
        ("session_expired.html", "login"),
    ],
)
def test_classify_search_page(fixture: str, expected: str) -> None:
    html = (FIXTURES / fixture).read_text(encoding="utf-8")
    assert classify_search_page(html, search_country_code="PK") == expected


def test_classify_spa_shell_unsupported() -> None:
    assert (
        classify_search_page("<html><body><div id='app'></div></body></html>", search_country_code="PK")
        == "unsupported"
    )

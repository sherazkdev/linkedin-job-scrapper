from datetime import UTC, datetime, timedelta

import pytest

from app.modules.collection.linkedin.parser import parse_search_job_cards
from app.modules.collection.linkedin.recency import (
    build_recency_rejection_diagnostic,
    is_within_past_24_hours,
    posting_age_hours,
)
from app.modules.jobs.posting_time import parse_posting_time
from tests.fixture_paths import LINKEDIN_FIXTURES as FIXTURES


def test_islamabad_card_relative_wins_over_date_only_iso() -> None:
    html = (FIXTURES / "search_page_job_search_card.html").read_text(encoding="utf-8")
    cards = parse_search_job_cards(html, search_country_code="PK")
    card = cards[0]
    ref = datetime(2026, 11, 15, 13, 0, tzinfo=UTC)
    posted, _ = parse_posting_time(
        iso_hint=card["posted_hint"],
        relative_text=card["posted_text"],
        reference=ref,
    )
    assert posted is not None
    assert is_within_past_24_hours(posted, reference=ref) is True
    assert posting_age_hours(posted, reference=ref) == pytest.approx(1.0)


def test_recency_exactly_24h_inclusive() -> None:
    now = datetime(2026, 1, 2, 12, 0, tzinfo=UTC)
    posted = now - timedelta(hours=24)
    assert is_within_past_24_hours(posted, reference=now) is True


def test_recency_just_over_24h() -> None:
    now = datetime(2026, 1, 2, 12, 0, tzinfo=UTC)
    posted = now - timedelta(hours=24, seconds=1)
    assert is_within_past_24_hours(posted, reference=now) is False


def test_recency_future_posted_at_is_recent() -> None:
    now = datetime(2026, 1, 2, 12, 0, tzinfo=UTC)
    posted = now + timedelta(minutes=5)
    assert is_within_past_24_hours(posted, reference=now) is True


def test_stale_search_card_fixture_iso() -> None:
    html = (FIXTURES / "search_page_1.html").read_text(encoding="utf-8")
    cards = parse_search_job_cards(html, search_country_code="DE")
    ref = datetime(2026, 11, 13, 12, 0, tzinfo=UTC)
    posted, _ = parse_posting_time(
        iso_hint=cards[0]["posted_hint"],
        relative_text=cards[0]["posted_text"],
        reference=ref,
    )
    assert posted is not None
    assert is_within_past_24_hours(posted, reference=ref) is False


def test_rejection_diagnostic_shape() -> None:
    now = datetime(2026, 11, 15, 12, 0, tzinfo=UTC)
    posted = now - timedelta(days=3)
    diag = build_recency_rejection_diagnostic(
        source_job_id="9102001",
        title="Junior ERP Consultant",
        posting_label="3 days ago",
        posted_at=posted,
        now=now,
        reason="stale",
    )
    assert diag["source_job_id"] == "9102001"
    assert diag["reason"] == "stale"
    assert diag["age_hours"] == pytest.approx(72.0)
    assert diag["posted_at_utc"].endswith("+00:00")
from datetime import UTC, datetime, timedelta

from app.modules.collection.linkedin.adapter import _build_search_url
from app.modules.collection.linkedin.locations import linkedin_search_location
from app.modules.collection.linkedin.recency import is_within_past_24_hours


def test_build_search_url_past_24_hours() -> None:
    url = _build_search_url(
        keyword="Software Engineer",
        location="Pakistan",
        start=0,
        past_24h=True,
    )
    assert "f_TPR=r86400" in url
    assert "Software+Engineer" in url or "Software%20Engineer" in url
    assert "Pakistan" in url


def test_pakistan_manifest_location() -> None:
    assert linkedin_search_location("PK") == "Pakistan"


def test_recency_within_24h() -> None:
    now = datetime.now(UTC)
    recent = now - timedelta(hours=2)
    assert is_within_past_24_hours(recent, reference=now) is True


def test_recency_stale() -> None:
    now = datetime.now(UTC)
    old = now - timedelta(days=3)
    assert is_within_past_24_hours(old, reference=now) is False


def test_recency_unknown() -> None:
    assert is_within_past_24_hours(None) is None


def test_collector_stats_adapter_rejections_are_separate() -> None:
    """Adapter pre-filter rejects do not increment normalization rejected_count."""
    from app.modules.collection.models.stats import CollectionStats

    stats = CollectionStats()
    stats.adapter_rejected_stale = 1
    assert stats.rejected_count == 0
    assert stats.collected_count == 0
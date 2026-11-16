from datetime import UTC, datetime, timedelta

from app.modules.jobs.posting_time import parse_posting_time, parse_relative_posting


def test_iso_and_relative_posting_prefers_more_recent_relative() -> None:
    ref = datetime(2026, 1, 15, 12, 0, tzinfo=UTC)
    posted, label = parse_posting_time(
        iso_hint="2026-01-10T08:00:00Z",
        relative_text="2 days ago",
        reference=ref,
    )
    assert posted is not None
    assert posted.day == 13
    assert label == "2 days ago"


def test_date_only_iso_ignored_when_relative_present() -> None:
    ref = datetime(2026, 11, 15, 13, 0, tzinfo=UTC)
    posted, label = parse_posting_time(
        iso_hint="2026-11-15",
        relative_text="1 hour ago",
        reference=ref,
    )
    assert posted == ref - timedelta(hours=1)
    assert label == "1 hour ago"


def test_reposted_relative_label() -> None:
    ref = datetime(2026, 3, 1, 12, 0, tzinfo=UTC)
    posted, label = parse_posting_time(
        iso_hint="2026-02-01T08:00:00Z",
        relative_text="Reposted 2 hours ago",
        reference=ref,
    )
    assert posted == ref - timedelta(hours=2)
    assert label == "Reposted 2 hours ago"


def test_relative_hours_with_reference() -> None:
    ref = datetime(2026, 3, 1, 12, 0, tzinfo=UTC)
    parsed = parse_relative_posting("3 hours ago", reference=ref)
    assert parsed is not None
    assert parsed < ref


def test_explicit_iso_timestamp_with_z() -> None:
    ref = datetime(2026, 3, 1, 12, 0, tzinfo=UTC)
    posted, _ = parse_posting_time(
        iso_hint="2026-03-01T09:30:00Z",
        relative_text=None,
        reference=ref,
    )
    assert posted == datetime(2026, 3, 1, 9, 30, tzinfo=UTC)


def test_unknown_posting_not_invented() -> None:
    posted, _ = parse_posting_time(iso_hint=None, relative_text="posted recently")
    assert posted is None


def test_malformed_iso_falls_back_to_relative() -> None:
    ref = datetime(2026, 1, 10, 12, 0, tzinfo=UTC)
    posted, _ = parse_posting_time(
        iso_hint="not-a-date",
        relative_text="5 minutes ago",
        reference=ref,
    )
    assert posted == ref - timedelta(minutes=5)


def test_date_only_iso_without_relative_is_unknown() -> None:
    posted, _ = parse_posting_time(iso_hint="2026-11-15", relative_text=None)
    assert posted is None
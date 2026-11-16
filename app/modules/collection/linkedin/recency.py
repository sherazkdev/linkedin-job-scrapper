"""Past-24-hours job recency checks (no invented timestamps)."""

from datetime import UTC, datetime, timedelta
from typing import Any

RECENCY_WINDOW = timedelta(hours=24)


def is_within_past_24_hours(
    posted_at: datetime | None,
    *,
    reference: datetime | None = None,
) -> bool | None:
    """
    Return True/False when posted_at is known; None when posting time is unknown.
    """
    if posted_at is None:
        return None
    ref = reference or datetime.now(UTC)
    posted = posted_at.astimezone(UTC)
    age = ref - posted
    return age <= RECENCY_WINDOW


def posting_age_hours(
    posted_at: datetime | None,
    *,
    reference: datetime | None = None,
) -> float | None:
    if posted_at is None:
        return None
    ref = reference or datetime.now(UTC)
    posted = posted_at.astimezone(UTC)
    return (ref - posted).total_seconds() / 3600.0


def build_recency_rejection_diagnostic(
    *,
    source_job_id: str,
    title: str | None,
    posting_label: str | None,
    posted_at: datetime | None,
    now: datetime,
    reason: str,
) -> dict[str, Any]:
    age = posting_age_hours(posted_at, reference=now)
    return {
        "source_job_id": source_job_id,
        "title": title,
        "posting_label": posting_label,
        "posted_at_utc": posted_at.astimezone(UTC).isoformat() if posted_at else None,
        "now_utc": now.astimezone(UTC).isoformat(),
        "age_hours": round(age, 3) if age is not None else None,
        "reason": reason,
    }
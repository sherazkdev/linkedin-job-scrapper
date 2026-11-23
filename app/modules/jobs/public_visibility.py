"""Public listing visibility rules (seven-day display lifetime, no last_seen reset)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

from app.modules.jobs.models.job import JobStatus


def _as_utc(value: Any) -> datetime | None:
    if value is None:
        return None
    if not isinstance(value, datetime):
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def effective_public_listing_date(doc: dict[str, Any]) -> datetime | None:
    """Age anchor for public display: posted_at when present, else first_seen_at."""
    posted = _as_utc(doc.get("posted_at"))
    if posted is not None:
        return posted
    return _as_utc(doc.get("first_seen_at"))


def posting_date_unknown(doc: dict[str, Any]) -> bool:
    return doc.get("posted_at") is None


def is_publicly_listable(
    doc: dict[str, Any],
    *,
    max_age_days: int,
    now: datetime | None = None,
) -> bool:
    if max_age_days <= 0:
        return str(doc.get("status") or "") == JobStatus.ACTIVE.value
    status = str(doc.get("status") or "")
    if status != JobStatus.ACTIVE.value:
        return False
    anchor = effective_public_listing_date(doc)
    if anchor is None:
        return False
    clock = now or datetime.now(UTC)
    cutoff = clock - timedelta(days=max_age_days)
    return anchor >= cutoff


def mongo_public_active_match(*, max_age_days: int, now: datetime | None = None) -> dict[str, Any]:
    """Mongo filter for jobs that should appear on the public site."""
    base: dict[str, Any] = {"status": JobStatus.ACTIVE.value}
    if max_age_days <= 0:
        return base
    return {"$and": [base, mongo_public_max_age_clause(max_age_days=max_age_days, now=now)]}


def mongo_public_max_age_clause(*, max_age_days: int, now: datetime | None = None) -> dict[str, Any]:
    """
    Jobs within the public display window.
    Uses posted_at when set; otherwise first_seen_at (unknown posting time fallback).
    """
    clock = now or datetime.now(UTC)
    cutoff = clock - timedelta(days=max_age_days)
    return {
        "$or": [
            {"posted_at": {"$gte": cutoff}},
            {
                "$and": [
                    {"$or": [{"posted_at": None}, {"posted_at": {"$exists": False}}]},
                    {"first_seen_at": {"$gte": cutoff}},
                ]
            },
        ]
    }
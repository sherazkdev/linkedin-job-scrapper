"""Posting time parsing with explicit UTC output."""

import re
from datetime import UTC, datetime, timedelta

_DATE_ONLY_ISO = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def parse_posting_time(
    *,
    iso_hint: str | None,
    relative_text: str | None,
    reference: datetime | None = None,
) -> tuple[datetime | None, str | None]:
    """
    Returns (posted_at_utc, source_label). Does not invent timestamps when unknown.

    When both an ISO datetime attribute and visible relative text are present,
    uses the more recent instant (LinkedIn often keeps an original listing date
    on reposts while showing e.g. "2 hours ago"). Date-only ISO values are ignored
    for timing because they lack time-of-day precision.
    """
    ref = reference or datetime.now(UTC)
    rel_dt = (
        parse_relative_posting(relative_text, reference=ref) if relative_text else None
    )
    iso_dt = _parse_iso_hint(iso_hint) if iso_hint else None

    if rel_dt is not None and iso_dt is not None:
        if rel_dt >= iso_dt:
            return rel_dt, relative_text.strip()
        return iso_dt, relative_text or iso_hint

    if rel_dt is not None:
        return rel_dt, relative_text.strip()
    if iso_dt is not None:
        return iso_dt, relative_text or iso_hint
    return None, relative_text or iso_hint


def _parse_iso_hint(iso_hint: str) -> datetime | None:
    stripped = iso_hint.strip()
    if _DATE_ONLY_ISO.match(stripped):
        return None
    try:
        parsed = datetime.fromisoformat(stripped.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def parse_relative_posting(text: str, *, reference: datetime) -> datetime | None:
    normalized = text.strip().lower()
    if "just now" in normalized:
        return reference.astimezone(UTC)
    match = re.search(r"(\d+)\s+(minute|hours?|day|days|week|weeks|month|months)", normalized)
    if not match:
        return None
    amount = int(match.group(1))
    unit = match.group(2)
    if unit.startswith("minute"):
        return reference.astimezone(UTC) - timedelta(minutes=amount)
    if unit.startswith("hour"):
        return reference.astimezone(UTC) - timedelta(hours=amount)
    if unit.startswith("day"):
        return reference.astimezone(UTC) - timedelta(days=amount)
    if unit.startswith("week"):
        return reference.astimezone(UTC) - timedelta(weeks=amount)
    if unit.startswith("month"):
        return reference.astimezone(UTC) - timedelta(days=amount * 30)
    return None
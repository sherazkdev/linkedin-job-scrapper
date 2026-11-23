"""Subscriber-level daily digest schedule (one timezone/time per subscriber)."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, time
from typing import Any
from zoneinfo import ZoneInfo

from app.modules.alerts.constants import EVENT_DIGEST


@dataclass(frozen=True, slots=True)
class DigestSchedule:
    timezone: str
    local_time: str  # HH:MM
    max_jobs: int


def schedule_from_digest_state(doc: dict[str, Any] | None) -> DigestSchedule | None:
    if not doc:
        return None
    tz = doc.get("digest_timezone")
    local_time = doc.get("digest_local_time")
    if not tz or not local_time:
        return None
    return DigestSchedule(
        timezone=str(tz),
        local_time=str(local_time),
        max_jobs=int(doc.get("digest_max_jobs") or 10),
    )


def digest_local_date_key(*, tz_name: str, now: datetime | None = None) -> str:
    now = now or datetime.now(UTC)
    local = now.astimezone(ZoneInfo(tz_name))
    return local.strftime("%Y-%m-%d")


def digest_event_key(*, tz_name: str, now: datetime | None = None, preview: bool = False) -> str:
    date_key = digest_local_date_key(tz_name=tz_name, now=now)
    if preview:
        from app.modules.alerts.constants import EVENT_DIGEST_PREVIEW

        return f"{EVENT_DIGEST_PREVIEW}:{date_key}"
    return f"{EVENT_DIGEST}:{date_key}"


def is_past_scheduled_time(*, schedule: DigestSchedule, now: datetime | None = None) -> bool:
    """True when local clock is at or after digest_local_time for the subscriber's day."""
    now = now or datetime.now(UTC)
    local = now.astimezone(ZoneInfo(schedule.timezone))
    hour, minute = (int(p) for p in schedule.local_time.split(":"))
    scheduled = time(hour=hour, minute=minute)
    return local.time() >= scheduled


def schedule_conflicts(existing: DigestSchedule, incoming: DigestSchedule) -> bool:
    return (
        existing.timezone != incoming.timezone
        or existing.local_time != incoming.local_time
        or existing.max_jobs != incoming.max_jobs
    )
"""Hard limit on live LinkedIn collection runs per rolling 24-hour window."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

from pymongo.asynchronous.database import AsyncDatabase

from app.core.config import Settings
from app.database.collection_indexes import COLLECTION_RUNS
from app.modules.collection.linkedin.errors import LinkedInCollectionError, LinkedInFailureState
from app.modules.collection.models.enums import CollectionRunStatus
from app.modules.jobs.models.job import JobSource


def _window_start(*, now: datetime | None = None) -> datetime:
    clock = now or datetime.now(UTC)
    return clock - timedelta(hours=24)


def _live_run_query(*, since: datetime) -> dict[str, Any]:
    return {
        "source": JobSource.LINKEDIN.value,
        "dry_run": False,
        "started_at": {"$gte": since},
        "status": {
            "$in": [
                CollectionRunStatus.RUNNING.value,
                CollectionRunStatus.COMPLETED.value,
                CollectionRunStatus.FAILED.value,
                CollectionRunStatus.CANCELLED.value,
            ]
        },
    }


async def count_live_linkedin_runs_24h(
    database: AsyncDatabase[Any],
    *,
    now: datetime | None = None,
) -> int:
    since = _window_start(now=now)
    return await database[COLLECTION_RUNS].count_documents(_live_run_query(since=since))


async def linkedin_daily_cap_snapshot(
    database: AsyncDatabase[Any],
    settings: Settings,
    *,
    now: datetime | None = None,
) -> dict[str, Any]:
    limit = max(int(settings.linkedin_max_live_runs_per_24h), 0)
    used = await count_live_linkedin_runs_24h(database, now=now)
    remaining = max(limit - used, 0) if limit > 0 else 0
    blocked = limit > 0 and used >= limit
    return {
        "limit": limit,
        "used_last_24h": used,
        "remaining": remaining,
        "blocked": blocked,
        "window_hours": 24,
    }


async def assert_live_linkedin_daily_cap(
    database: AsyncDatabase[Any],
    settings: Settings,
    *,
    now: datetime | None = None,
) -> None:
    """Raise when live LinkedIn collection would exceed the configured 24h cap."""
    if not settings.allow_live_linkedin_collection:
        return
    limit = max(int(settings.linkedin_max_live_runs_per_24h), 0)
    if limit <= 0:
        return
    snapshot = await linkedin_daily_cap_snapshot(database, settings, now=now)
    if snapshot["blocked"]:
        raise LinkedInCollectionError(
            LinkedInFailureState.RATE_LIMITED,
            (
                f"LinkedIn daily live run cap reached "
                f"({snapshot['used_last_24h']}/{limit} in 24h); "
                "dispatch blocked until window rolls forward"
            ),
            retryable=False,
        )


def live_linkedin_cap_enforced(settings: Settings) -> bool:
    return (
        settings.allow_live_linkedin_collection
        and max(int(settings.linkedin_max_live_runs_per_24h), 0) > 0
    )
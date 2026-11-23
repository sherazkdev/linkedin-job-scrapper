"""High-level scraper operational status (no secrets)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from enum import StrEnum
from typing import Any

from pymongo.asynchronous.database import AsyncDatabase

from app.core.config import Settings
from app.database.collection_indexes import COLLECTION_RUNS, COLLECTION_TARGETS
from app.modules.collection.models.enums import CollectionRunStatus
from app.modules.collection.operations.failure_classifier import (
    CollectionFailureKind,
    classify_error_summary,
    is_auth_or_verification,
)
from app.modules.scheduling.linkedin_daily_cap import linkedin_daily_cap_snapshot


class CollectionOperationalStatus(StrEnum):
    RUNNING = "RUNNING"
    PAUSED_DAILY_CAP = "PAUSED_DAILY_CAP"
    AUTH_REQUIRED = "AUTH_REQUIRED"
    VERIFICATION_REQUIRED = "VERIFICATION_REQUIRED"
    DEGRADED = "DEGRADED"
    STOPPED = "STOPPED"
    HEALTHY = "HEALTHY"


async def resolve_collection_status(
    database: AsyncDatabase[Any],
    settings: Settings,
) -> dict[str, Any]:
    now = datetime.now(UTC)
    enabled_targets = await database[COLLECTION_TARGETS].count_documents(
        {"source": "linkedin", "enabled": True}
    )
    cap = await linkedin_daily_cap_snapshot(database, settings)
    cap_blocked = bool(cap and cap.get("blocked"))

    last_success = await database[COLLECTION_RUNS].find_one(
        {
            "source": "linkedin",
            "dry_run": False,
            "status": CollectionRunStatus.COMPLETED.value,
        },
        sort=[("finished_at", -1)],
    )
    last_new_job = await database["jobs"].find_one(
        {"source": "linkedin"},
        sort=[("first_seen_at", -1)],
        projection={"first_seen_at": 1},
    )
    last_fail = await database[COLLECTION_RUNS].find_one(
        {
            "source": "linkedin",
            "dry_run": False,
            "status": CollectionRunStatus.FAILED.value,
        },
        sort=[("finished_at", -1)],
    )
    fail_kind = classify_error_summary(
        str(last_fail.get("error_summary") if last_fail else "")
    )
    auth_recent = await database[COLLECTION_RUNS].count_documents(
        {
            "source": "linkedin",
            "dry_run": False,
            "status": CollectionRunStatus.FAILED.value,
            "started_at": {"$gte": now - timedelta(hours=24)},
            "error_summary": {"$regex": "authentication|verification|session", "$options": "i"},
        }
    )

    collection_enabled = (
        settings.allow_live_linkedin_collection
        and settings.celery_allow_linkedin_tasks
        and enabled_targets > 0
    )

    status = CollectionOperationalStatus.STOPPED
    if not collection_enabled:
        status = CollectionOperationalStatus.STOPPED
    elif cap_blocked:
        status = CollectionOperationalStatus.PAUSED_DAILY_CAP
    elif fail_kind == CollectionFailureKind.VERIFICATION_REQUIRED or (
        auth_recent and "verification" in str(last_fail.get("error_summary", "")).lower()
    ):
        status = CollectionOperationalStatus.VERIFICATION_REQUIRED
    elif fail_kind == CollectionFailureKind.AUTH_REQUIRED or auth_recent >= 1:
        status = CollectionOperationalStatus.AUTH_REQUIRED
    elif collection_enabled and last_success:
        status = CollectionOperationalStatus.HEALTHY
    elif collection_enabled:
        status = CollectionOperationalStatus.RUNNING

    no_new_hours = settings.collection_no_new_jobs_alert_hours
    stale_discovery = False
    if last_new_job and last_new_job.get("first_seen_at"):
        fs = last_new_job["first_seen_at"]
        if fs.tzinfo is None:
            fs = fs.replace(tzinfo=UTC)
        stale_discovery = (now - fs) > timedelta(hours=no_new_hours)

    if (
        status == CollectionOperationalStatus.HEALTHY
        and stale_discovery
        and collection_enabled
    ):
        status = CollectionOperationalStatus.DEGRADED

    return {
        "status": status.value,
        "collection_enabled": collection_enabled,
        "enabled_linkedin_targets": enabled_targets,
        "allow_live_linkedin_collection": settings.allow_live_linkedin_collection,
        "linkedin_daily_cap": cap,
        "last_successful_collection_at": (
            last_success.get("finished_at").isoformat()
            if last_success and last_success.get("finished_at")
            else None
        ),
        "last_new_job_at": (
            last_new_job.get("first_seen_at").isoformat()
            if last_new_job and last_new_job.get("first_seen_at")
            else None
        ),
        "latest_collection_error": {
            "kind": fail_kind.value,
            "at": (
                last_fail.get("finished_at").isoformat()
                if last_fail and last_fail.get("finished_at")
                else None
            ),
            "summary_prefix": (
                str(last_fail.get("error_summary") or "")[:120] if last_fail else None
            ),
            "auth_or_verification": is_auth_or_verification(fail_kind),
        },
        "alerts": {
            "no_new_jobs_within_hours": no_new_hours,
            "no_new_jobs_triggered": stale_discovery,
        },
    }
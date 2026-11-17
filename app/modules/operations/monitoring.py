"""Sanitized collection and job-store operational metrics."""

from datetime import UTC, datetime
from typing import Any

from pymongo.asynchronous.database import AsyncDatabase

from app.core.config import get_settings
from app.database.collection_indexes import COLLECTION_RUNS, COLLECTION_TARGETS
from app.database.indexes import JOBS_COLLECTION
from app.modules.collection.models.enums import CollectionRunStatus
from app.modules.collection.repositories.target_repository import TargetRepository
from app.modules.scheduling.linkedin_daily_cap import linkedin_daily_cap_snapshot
from app.modules.scheduling.rollout import estimate_daily_throughput, scheduling_architecture_snapshot
from app.workers.policy import allowed_task_sources


async def build_operations_snapshot(database: AsyncDatabase[Any]) -> dict[str, Any]:
    jobs = database[JOBS_COLLECTION]
    runs = database[COLLECTION_RUNS]
    now = datetime.now(UTC)

    total_jobs = await jobs.count_documents({})
    by_source = await _aggregate_counts(jobs, "$source")
    by_status = await _aggregate_counts(jobs, "$status")
    by_job_country = await _aggregate_counts(jobs, "$country_code")

    failed_runs_24h = await runs.count_documents(
        {
            "status": CollectionRunStatus.FAILED.value,
            "finished_at": {"$gte": now.replace(hour=0, minute=0, second=0, microsecond=0)},
        }
    )
    running_runs = await runs.count_documents({"status": CollectionRunStatus.RUNNING.value})

    target_repo = TargetRepository(database)
    settings = get_settings()
    eligible = await target_repo.list_eligible_targets(
        allowed_sources=list(allowed_task_sources(settings)),
        limit=50,
    )
    pending = await database[COLLECTION_TARGETS].count_documents(
        {
            "enabled": True,
            "$or": [
                {"next_eligible_at": None},
                {"next_eligible_at": {"$lte": now}},
            ],
        }
    )

    recent_runs = (
        await runs.find({})
        .sort("started_at", -1)
        .limit(10)
        .to_list(length=10)
    )
    durations_ms: list[float] = []
    for run in recent_runs:
        if run.get("started_at") and run.get("finished_at"):
            delta = run["finished_at"] - run["started_at"]
            durations_ms.append(delta.total_seconds() * 1000)

    last_success: list[dict[str, Any]] = []
    cursor = database[COLLECTION_TARGETS].find({"last_success_at": {"$ne": None}})
    async for doc in cursor:
        last_success.append(
            {
                "source": doc.get("source"),
                "country_code": doc.get("country_code"),
                "keyword": doc.get("keyword"),
                "last_success_at": doc.get("last_success_at"),
                "next_eligible_at": doc.get("next_eligible_at"),
            }
        )

    stats_totals = {"created": 0, "updated": 0, "unchanged": 0, "rejected": 0, "failed": 0}
    for run in recent_runs:
        for key, field in (
            ("created", "created_count"),
            ("updated", "updated_count"),
            ("unchanged", "unchanged_count"),
            ("rejected", "rejected_count"),
            ("failed", "failed_count"),
        ):
            stats_totals[key] += int(run.get(field) or 0)

    scheduling = scheduling_architecture_snapshot(settings)
    try:
        throughput = estimate_daily_throughput(settings)
    except FileNotFoundError:
        throughput = None
    try:
        linkedin_cap = await linkedin_daily_cap_snapshot(database, settings)
    except Exception:
        linkedin_cap = None

    return {
        "generated_at": now.isoformat(),
        "jobs": {
            "total": total_jobs,
            "by_source": by_source,
            "by_status": by_status,
            "by_job_country_code": by_job_country,
        },
        "collection": {
            "running_runs": running_runs,
            "failed_runs_today": failed_runs_24h,
            "pending_eligible_targets": pending,
            "dispatch_sample_eligible": len(eligible),
            "recent_run_stats": stats_totals,
            "recent_avg_duration_ms": (
                (sum(durations_ms) / len(durations_ms)) if durations_ms else None
            ),
            "last_success_per_target": last_success[:25],
        },
        "scheduling": {
            **scheduling,
            "throughput_estimate": throughput,
            "linkedin_daily_cap": linkedin_cap,
            "scheduling_lag_hint": (
                "eligible_pending minus recent completions; use celery_ops queue_depth between ticks"
            ),
        },
    }


async def _aggregate_counts(collection: Any, field: str) -> dict[str, int]:
    pipeline = [{"$group": {"_id": field, "count": {"$sum": 1}}}]
    result: dict[str, int] = {}
    cursor = await collection.aggregate(pipeline)
    async for row in cursor:
        key = row["_id"] if row["_id"] is not None else "unknown"
        result[str(key)] = int(row["count"])
    return result
"""Daily unique-job throughput metrics (discovery vs publication)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

from pymongo.asynchronous.database import AsyncDatabase

from app.database.collection_indexes import COLLECTION_RUNS
from app.database.indexes import JOBS_COLLECTION
from app.modules.collection.models.enums import CollectionRunStatus


async def aggregate_daily_throughput(
    database: AsyncDatabase[Any],
    *,
    window_hours: int = 24,
    source: str = "linkedin",
) -> dict[str, Any]:
    now = datetime.now(UTC)
    since = now - timedelta(hours=window_hours)
    day_start = now.replace(hour=0, minute=0, second=0, microsecond=0)

    runs = database[COLLECTION_RUNS]
    jobs = database[JOBS_COLLECTION]

    run_match = {"source": source, "dry_run": False, "started_at": {"$gte": since}}
    agg = await runs.aggregate(
        [
            {"$match": run_match},
            {
                "$group": {
                    "_id": None,
                    "created": {"$sum": {"$ifNull": ["$created_count", 0]}},
                    "updated": {"$sum": {"$ifNull": ["$updated_count", 0]}},
                    "unchanged": {"$sum": {"$ifNull": ["$unchanged_count", 0]}},
                    "rejected": {"$sum": {"$ifNull": ["$rejected_count", 0]}},
                    "failed_items": {"$sum": {"$ifNull": ["$failed_count", 0]}},
                    "completed": {
                        "$sum": {
                            "$cond": [
                                {"$eq": ["$status", CollectionRunStatus.COMPLETED.value]},
                                1,
                                0,
                            ]
                        }
                    },
                    "failed_runs": {
                        "$sum": {
                            "$cond": [
                                {"$eq": ["$status", CollectionRunStatus.FAILED.value]},
                                1,
                                0,
                            ]
                        }
                    },
                }
            },
        ]
    ).to_list(length=1)
    run_totals = agg[0] if agg else {}

    unique_new_24h = await jobs.count_documents(
        {
            "source": source,
            "first_seen_at": {"$gte": since},
        }
    )
    unique_new_today = await jobs.count_documents(
        {
            "source": source,
            "first_seen_at": {"$gte": day_start},
        }
    )

    by_keyword = await runs.aggregate(
        [
            {"$match": {**run_match, "status": CollectionRunStatus.COMPLETED.value}},
            {"$group": {"_id": "$keyword", "created": {"$sum": {"$ifNull": ["$created_count", 0]}}}},
            {"$sort": {"created": -1}},
            {"$limit": 30},
        ]
    ).to_list(length=30)

    by_country = await runs.aggregate(
        [
            {"$match": {**run_match, "status": CollectionRunStatus.COMPLETED.value}},
            {"$group": {"_id": "$country_code", "created": {"$sum": {"$ifNull": ["$created_count", 0]}}}},
            {"$sort": {"created": -1}},
            {"$limit": 40},
        ]
    ).to_list(length=40)

    return {
        "window_hours": window_hours,
        "since": since.isoformat(),
        "unique_jobs_created_24h": unique_new_24h,
        "unique_jobs_created_today": unique_new_today,
        "run_stats": {
            "created_from_runs": int(run_totals.get("created", 0)),
            "updated_from_runs": int(run_totals.get("updated", 0)),
            "unchanged_from_runs": int(run_totals.get("unchanged", 0)),
            "rejected_from_runs": int(run_totals.get("rejected", 0)),
            "failed_item_count": int(run_totals.get("failed_items", 0)),
            "completed_runs": int(run_totals.get("completed", 0)),
            "failed_runs": int(run_totals.get("failed_runs", 0)),
        },
        "created_by_keyword": [
            {"keyword": row["_id"], "created": int(row.get("created", 0))} for row in by_keyword
        ],
        "created_by_country": [
            {"country_code": row["_id"], "created": int(row.get("created", 0))} for row in by_country
        ],
    }
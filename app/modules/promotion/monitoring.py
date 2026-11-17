"""Read-only publication & collection health metrics (pilot DB + production DB)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

from pymongo.asynchronous.database import AsyncDatabase

from app.database.collection_indexes import COLLECTION_RUNS
from app.database.indexes import JOBS_COLLECTION
from app.modules.collection.models.enums import CollectionRunStatus
from app.modules.jobs.models.job import JobDataProvenance, JobSource, JobStatus
from app.modules.promotion.pilot_to_production import ELIGIBLE_QUERY, PROMOTION_AUDIT_COLLECTION
from app.modules.promotion.publication_sync import (
    analyze_publication_sync,
    fetch_production_published,
)

AUTH_FAILURE_PATTERN = [
    {"error_summary": {"$regex": "authentication", "$options": "i"}},
    {"error_summary": {"$regex": "verification", "$options": "i"}},
    {"error_summary": {"$regex": "session", "$options": "i"}},
    {"error_summary": {"$regex": "access_denied", "$options": "i"}},
]


async def collect_publication_metrics(
    *,
    pilot_db: AsyncDatabase[Any],
    production_db: AsyncDatabase[Any],
    observation_start: datetime | None = None,
) -> dict[str, Any]:
    now = datetime.now(UTC)
    day_ago = now - timedelta(hours=24)
    week_ago = now - timedelta(days=7)

    pilot_eligible = await pilot_db[JOBS_COLLECTION].count_documents(ELIGIBLE_QUERY)
    prod_published = await production_db[JOBS_COLLECTION].count_documents(ELIGIBLE_QUERY)
    posted_24h_pilot = await pilot_db[JOBS_COLLECTION].count_documents(
        {**ELIGIBLE_QUERY, "posted_at": {"$gte": day_ago}}
    )
    posted_24h_prod = await production_db[JOBS_COLLECTION].count_documents(
        {**ELIGIBLE_QUERY, "posted_at": {"$gte": day_ago}}
    )

    sync = await analyze_publication_sync(pilot_db, production_db, enforce_db_names=False)
    lag_count = len(sync.get("sync_plan", {}).get("publication_lag_samples") or [])

    runs_since = observation_start or day_ago
    run_filter = {
        "source": JobSource.LINKEDIN.value,
        "dry_run": False,
        "started_at": {"$gte": runs_since},
    }
    runs_completed = await pilot_db[COLLECTION_RUNS].count_documents(
        {**run_filter, "status": CollectionRunStatus.COMPLETED.value}
    )
    runs_failed = await pilot_db[COLLECTION_RUNS].count_documents(
        {**run_filter, "status": CollectionRunStatus.FAILED.value}
    )
    auth_failures = await pilot_db[COLLECTION_RUNS].count_documents(
        {
            **run_filter,
            "status": CollectionRunStatus.FAILED.value,
            "$or": AUTH_FAILURE_PATTERN,
        }
    )

    enabled_targets = await pilot_db["collection_targets"].count_documents(
        {"source": JobSource.LINKEDIN.value, "enabled": True}
    )

    last_promo = await production_db[PROMOTION_AUDIT_COLLECTION].find_one(
        {
            "$or": [
                {"type": {"$exists": False}},
                {"type": {"$nin": ["deprecation"]}},
            ]
        },
        sort=[("created_at", -1)],
    )
    last_deprecation = await production_db[PROMOTION_AUDIT_COLLECTION].find_one(
        {"type": "deprecation"},
        sort=[("created_at", -1)],
    )

    coverage_cursor = await pilot_db[JOBS_COLLECTION].aggregate(
        [
            {"$match": ELIGIBLE_QUERY},
            {"$group": {"_id": "$search_country_code", "count": {"$sum": 1}}},
            {"$sort": {"count": -1}},
        ]
    )
    coverage = await coverage_cursor.to_list(length=50)

    prod_docs = await fetch_production_published(production_db)
    promoted_ages: list[float] = []
    for doc in prod_docs:
        promoted = doc.get("promoted_from_pilot_at")
        if isinstance(promoted, datetime):
            if promoted.tzinfo is None:
                promoted = promoted.replace(tzinfo=UTC)
            promoted_ages.append((now - promoted).total_seconds())

    return {
        "generated_at": now.isoformat(),
        "job_freshness": {
            "pilot_eligible_active": pilot_eligible,
            "production_published_active": prod_published,
            "pilot_posted_last_24h": posted_24h_pilot,
            "production_posted_last_24h": posted_24h_prod,
            "pilot_vs_production_eligible_delta": pilot_eligible - prod_published,
        },
        "publication_sync": {
            "would_create": sync.get("sync_plan", {}).get("would_create_count", 0),
            "would_deprecate": sync.get("sync_plan", {}).get("would_deprecate_count", 0),
            "pilot_ahead_of_production_samples": lag_count,
        },
        "collection_health_24h_or_since_start": {
            "window_start": runs_since.isoformat(),
            "completed_runs": runs_completed,
            "failed_runs": runs_failed,
            "auth_class_failures": auth_failures,
            "enabled_linkedin_targets": enabled_targets,
        },
        "coverage_by_search_market_pilot": coverage,
        "last_promotion_batch": (
            {
                "batch_id": last_promo.get("batch_id"),
                "created_count": last_promo.get("created_count"),
                "updated_count": last_promo.get("updated_count"),
                "created_at": last_promo.get("created_at"),
            }
            if last_promo
            else None
        ),
        "last_deprecation_batch": last_deprecation,
        "promotion_age_seconds_max": max(promoted_ages) if promoted_ages else None,
        "promotion_age_seconds_min": min(promoted_ages) if promoted_ages else None,
    }
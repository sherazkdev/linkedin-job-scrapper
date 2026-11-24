"""Read-only audit: newest production jobs and pilot synthetic residue."""

from __future__ import annotations

import asyncio
import json
from datetime import datetime
from typing import Any

from app.database.collection_indexes import COLLECTION_RUNS
from app.database.temp_database import open_database
from app.modules.promotion.pilot_to_production import PROMOTION_AUDIT_COLLECTION


def _json_default(value: Any) -> Any:
    if isinstance(value, datetime):
        return value.isoformat()
    return str(value)


def _job_row(doc: dict[str, Any]) -> dict[str, Any]:
    return {
        "source": doc.get("source"),
        "sourceJobId": doc.get("sourceJobId"),
        "data_provenance": doc.get("data_provenance"),
        "first_seen_at": doc.get("first_seen_at"),
        "posted_at": doc.get("posted_at"),
        "promoted_from_pilot_at": doc.get("promoted_from_pilot_at"),
        "promotion_batch_id": doc.get("promotion_batch_id"),
        "status": doc.get("status"),
        "country_code": doc.get("country_code"),
        "title": (doc.get("title") or "")[:120],
    }


async def main() -> None:
    async with open_database("global_jobs") as prod:
        total = await prod.jobs.count_documents({})
        active = await prod.jobs.count_documents({"status": "active"})
        synth = await prod.jobs.count_documents({"source": "integration_test"})
        promoted_recent = await prod.jobs.count_documents({"promotion_batch_id": {"$exists": True}})
        cursor = prod.jobs.find({}).sort("first_seen_at", -1).limit(15)
        newest = await cursor.to_list(length=15)
        promo_cursor = (
            prod[PROMOTION_AUDIT_COLLECTION]
            .find({})
            .sort("applied_at", -1)
            .limit(5)
        )
        promo_batches = await promo_cursor.to_list(length=5)
        run_cursor = prod[COLLECTION_RUNS].find({}).sort("started_at", -1).limit(5)
        collection_runs = await run_cursor.to_list(length=5)
    async with open_database("global_jobs_pilot") as pilot:
        ptotal = await pilot.jobs.count_documents({})
        psynth = await pilot.jobs.count_documents({"source": "integration_test"})
        subs = await pilot.alert_subscribers.count_documents({"purpose": "integration_test"})
        pnotif_test = await pilot.alert_notifications.count_documents(
            {"purpose": "integration_test"}
        )

    payload = {
        "production_total": total,
        "production_active": active,
        "production_integration_test_source": synth,
        "production_with_promotion_batch_id": promoted_recent,
        "production_newest_by_first_seen": [_job_row(d) for d in newest],
        "production_recent_promotion_batches": [
            {
                "batch_id": b.get("batch_id"),
                "applied_at": b.get("applied_at"),
                "created": b.get("created"),
                "updated": b.get("updated"),
                "skipped": b.get("skipped"),
            }
            for b in promo_batches
        ],
        "production_recent_collection_runs": [
            {
                "country_code": r.get("country_code"),
                "status": r.get("status"),
                "started_at": r.get("started_at"),
                "finished_at": r.get("finished_at"),
                "jobs_new": r.get("jobs_new"),
                "jobs_updated": r.get("jobs_updated"),
            }
            for r in collection_runs
        ],
        "pilot_total": ptotal,
        "pilot_integration_test_jobs": psynth,
        "pilot_integration_test_subscribers": subs,
        "pilot_integration_test_notifications": pnotif_test,
    }
    print(json.dumps(payload, indent=2, default=_json_default))


if __name__ == "__main__":
    asyncio.run(main())
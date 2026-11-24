"""Read-only audit: newest production jobs and pilot synthetic residue."""

from __future__ import annotations

import asyncio
import json

from app.database.temp_database import open_database


async def main() -> None:
    async with open_database("global_jobs") as prod:
        total = await prod.jobs.count_documents({})
        synth = await prod.jobs.count_documents({"source": "integration_test"})
        cursor = await prod.jobs.find({}).sort("first_seen_at", -1).limit(15)
        newest = await cursor.to_list(length=15)
    async with open_database("global_jobs_pilot") as pilot:
        ptotal = await pilot.jobs.count_documents({})
        psynth = await pilot.jobs.count_documents({"source": "integration_test"})
        subs = await pilot.alert_subscribers.count_documents({"purpose": "integration_test"})
    payload = {
        "production_total": total,
        "production_integration_test_source": synth,
        "production_newest": [
            {
                "source": d.get("source"),
                "sourceJobId": d.get("sourceJobId"),
                "data_provenance": d.get("data_provenance"),
                "first_seen_at": str(d.get("first_seen_at")),
                "posted_at": str(d.get("posted_at")),
                "promoted_from_pilot_at": d.get("promoted_from_pilot_at"),
                "title": d.get("title"),
            }
            for d in newest
        ],
        "pilot_total": ptotal,
        "pilot_integration_test_jobs": psynth,
        "pilot_integration_test_subscribers": subs,
    }
    print(json.dumps(payload, indent=2))


if __name__ == "__main__":
    asyncio.run(main())
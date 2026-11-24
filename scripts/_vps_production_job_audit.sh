#!/usr/bin/env bash
# Read-only: explain production job count delta vs pilot promotion/synthetic sources.
set -euo pipefail
docker exec linkedin-scraper-api python <<'PY'
import asyncio
import json
from datetime import UTC, datetime

from app.database.temp_database import open_database


async def main() -> None:
    async with open_database("global_jobs") as prod:
        total = await prod.jobs.count_documents({})
        synth = await prod.jobs.count_documents({"source": "integration_test"})
        pilot_tag = await prod.jobs.count_documents({"integration_test": True})
        recent = await prod.jobs.find({}).sort("first_seen_at", -1).limit(12).to_list(12)
        newest_ids = [
            {
                "source": d.get("source"),
                "sourceJobId": d.get("sourceJobId"),
                "data_provenance": d.get("data_provenance"),
                "first_seen_at": str(d.get("first_seen_at")),
                "posted_at": str(d.get("posted_at")),
                "title": (d.get("title") or "")[:80],
                "country_code": d.get("country_code"),
            }
            for d in recent
        ]
    async with open_database("global_jobs_pilot") as pilot:
        ptotal = await pilot.jobs.count_documents({})
        psynth = await pilot.jobs.count_documents({"source": "integration_test"})
        pint = await pilot.jobs.count_documents({"integration_test": True})
        palert_subs = await pilot.alert_subscribers.count_documents({"purpose": "integration_test"})
        pnotif = await pilot.alert_notifications.count_documents({})
    print(json.dumps({
        "production_total": total,
        "production_integration_test_source": synth,
        "production_integration_test_flag": pilot_tag,
        "production_newest_by_first_seen": newest_ids,
        "pilot_total": ptotal,
        "pilot_integration_test_jobs": psynth,
        "pilot_integration_test_flag": pint,
        "pilot_integration_test_subscribers": palert_subs,
        "pilot_notifications_remaining": pnotif,
    }, indent=2))

asyncio.run(main())
PY
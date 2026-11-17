"""Read-only inspect global_jobs_pilot LinkedIn jobs (ops CLI)."""

from __future__ import annotations

import asyncio
import json
import os
import sys

from pymongo import AsyncMongoClient


async def main() -> None:
    db_name = os.environ.get("PILOT_DB", "global_jobs_pilot")
    uri = os.environ["MONGO_URI"]
    client = AsyncMongoClient(uri, serverSelectionTimeoutMS=10_000)
    db = client[db_name]
    await client.admin.command("ping")

    countries = ("PK", "GB", "US", "DE", "AE")
    out: dict[str, object] = {"db": db_name, "countries": {}}
    for cc in countries:
        search_docs = await db.jobs.find(
            {"source": "linkedin", "search_country_code": cc},
            {
                "_id": 0,
                "sourceJobId": 1,
                "title": 1,
                "country_code": 1,
                "search_country_code": 1,
                "location_text": 1,
                "data_provenance": 1,
            },
        ).to_list(50)
        job_country_count = await db.jobs.count_documents(
            {"source": "linkedin", "country_code": cc}
        )
        out["countries"][cc] = {
            "by_search_country_code": len(search_docs),
            "by_job_country_code": job_country_count,
            "jobs": search_docs,
        }
    out["total"] = await db.jobs.count_documents({"source": "linkedin"})
    print(json.dumps(out, indent=2, default=str))
    await client.close()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyError as exc:
        print(f"missing env: {exc}", file=sys.stderr)
        raise SystemExit(2) from exc
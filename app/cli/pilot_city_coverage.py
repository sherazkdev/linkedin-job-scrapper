"""Read-only pilot job.city coverage report."""

from __future__ import annotations

import asyncio
import json

from app.core.config import get_settings
from app.database.temp_database import open_database


async def report() -> dict:
    settings = get_settings()
    async with open_database(settings.mongo_db_name) as db:
        total = await db.jobs.count_documents({})
        with_city = await db.jobs.count_documents(
            {"city": {"$exists": True, "$type": "string", "$nin": ["", None]}}
        )
        location_only = await db.jobs.count_documents(
            {
                "$and": [
                    {"location_text": {"$exists": True, "$nin": [None, ""]}},
                    {"$or": [{"city": {"$exists": False}}, {"city": None}, {"city": ""}]},
                ]
            }
        )
        pk_total = await db.jobs.count_documents(
            {"$or": [{"country_code": "PK"}, {"search_country_code": "PK"}]}
        )
        pk_city = await db.jobs.count_documents(
            {
                "$or": [{"country_code": "PK"}, {"search_country_code": "PK"}],
                "city": {"$exists": True, "$type": "string", "$nin": ["", None]},
            }
        )
        isb = await db.jobs.count_documents(
            {
                "city": {"$regex": r"^(Islamabad|Rawalpindi)$", "$options": "i"},
            }
        )
        by_country = await db.jobs.aggregate(
            [
                {
                    "$group": {
                        "_id": {"$ifNull": ["$country_code", "$search_country_code"]},
                        "total": {"$sum": 1},
                        "with_city": {
                            "$sum": {
                                "$cond": [
                                    {
                                        "$and": [
                                            {"$ne": ["$city", None]},
                                            {"$ne": ["$city", ""]},
                                        ]
                                    },
                                    1,
                                    0,
                                ]
                            }
                        },
                    }
                },
                {"$sort": {"total": -1}},
                {"$limit": 30},
            ]
        ).to_list(30)
        return {
            "database": settings.mongo_db_name,
            "jobs_total": total,
            "jobs_with_structured_city": with_city,
            "jobs_missing_city": total - with_city,
            "city_population_pct": round((with_city / total * 100) if total else 0, 2),
            "location_text_without_city": location_only,
            "pakistan_jobs": pk_total,
            "pakistan_with_city": pk_city,
            "pakistan_city_pct": round((pk_city / pk_total * 100) if pk_total else 0, 2),
            "islamabad_rawalpindi_jobs": isb,
            "by_country_sample": by_country,
        }


def main() -> None:
    print(json.dumps(asyncio.run(report()), indent=2))


if __name__ == "__main__":
    main()
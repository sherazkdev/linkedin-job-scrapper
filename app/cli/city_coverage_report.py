"""Read-only structured city coverage for any Mongo jobs database."""

from __future__ import annotations

import argparse
import asyncio
import json

from app.database.temp_database import open_database


async def report(db_name: str) -> dict:
    async with open_database(db_name) as db:
        total = await db.jobs.count_documents({})
        with_city = await db.jobs.count_documents(
            {"city": {"$exists": True, "$type": "string", "$nin": ["", None]}}
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
        isb = await db.jobs.count_documents({"city": {"$regex": r"^Islamabad$", "$options": "i"}})
        rwp = await db.jobs.count_documents({"city": {"$regex": r"^Rawalpindi$", "$options": "i"}})
        cursor = db.jobs.aggregate(
            [
                {
                    "$group": {
                        "_id": {"$ifNull": ["$country_code", "$search_country_code"]},
                        "total": {"$sum": 1},
                        "with_city": {
                            "$sum": {
                                "$cond": [
                                    {"$and": [{"$ne": ["$city", None]}, {"$ne": ["$city", ""]}]},
                                    1,
                                    0,
                                ]
                            }
                        },
                    }
                },
                {"$sort": {"total": -1}},
                {"$limit": 25},
            ]
        )
        by_country = await cursor.to_list(length=25)
        return {
            "database": db_name,
            "jobs_total": total,
            "jobs_with_structured_city": with_city,
            "city_population_pct": round((with_city / total * 100) if total else 0, 2),
            "pakistan_jobs": pk_total,
            "pakistan_with_city": pk_city,
            "islamabad_jobs": isb,
            "rawalpindi_jobs": rwp,
            "by_country_sample": by_country,
        }


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--database", default="global_jobs_pilot")
    args = p.parse_args()
    print(json.dumps(asyncio.run(report(args.database)), indent=2))


if __name__ == "__main__":
    main()
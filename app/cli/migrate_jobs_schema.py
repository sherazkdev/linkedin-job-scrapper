"""Idempotent job schema backfill (search_country_code only; no invented geo)."""

import argparse
import asyncio
import logging

from pymongo import UpdateOne

from app.core.config import get_settings
from app.core.logging import configure_logging
from app.database.indexes import ensure_job_indexes
from app.database.temp_database import open_database

logger = logging.getLogger(__name__)


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Backfill job geography fields safely")
    parser.add_argument("--mongo-db", required=True)
    parser.add_argument("--dry-run", action="store_true", default=True)
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Set --dry-run false and apply updates",
    )
    return parser.parse_args()


async def migrate(db_name: str, *, dry_run: bool) -> dict[str, int]:
    async with open_database(db_name) as database:
        await ensure_job_indexes(database)
        jobs = database["jobs"]
        cursor = jobs.find(
            {
                "search_country_code": {"$exists": False},
                "country_code": {"$exists": True, "$type": "string"},
            }
        )
        ops: list[UpdateOne] = []
        scanned = 0
        async for doc in cursor:
            scanned += 1
            cc = doc.get("country_code")
            if not isinstance(cc, str) or len(cc) != 2:
                continue
            ops.append(
                UpdateOne(
                    {"_id": doc["_id"]},
                    {"$set": {"search_country_code": cc.upper()}},
                )
            )
        if dry_run:
            return {
                "scanned_missing_search_country": scanned,
                "would_update": len(ops),
                "updated": 0,
            }
        if ops:
            result = await jobs.bulk_write(ops, ordered=False)
            return {
                "scanned_missing_search_country": scanned,
                "would_update": len(ops),
                "updated": result.modified_count,
            }
        return {"scanned_missing_search_country": scanned, "would_update": 0, "updated": 0}


def main() -> None:
    settings = get_settings()
    configure_logging(settings)
    args = _parse_args()
    dry_run = not args.apply
    if args.mongo_db == settings.mongo_db_name and not settings.allow_collection_production_db:
        raise SystemExit("Refusing production DB without ALLOW_COLLECTION_PRODUCTION_DB=true")
    summary = asyncio.run(migrate(args.mongo_db, dry_run=dry_run))
    logger.info("Migration summary dry_run=%s %s", dry_run, summary)
    print(summary)


if __name__ == "__main__":
    main()
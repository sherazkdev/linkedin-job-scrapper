"""Backfill jobs.data_provenance from source metadata (dry-run default)."""

import argparse
import asyncio
import json
import logging

from pymongo import UpdateOne

from app.core.config import get_settings
from app.core.logging import configure_logging
from app.database.indexes import ensure_job_indexes
from app.database.temp_database import open_database
from app.modules.jobs.provenance import infer_provenance_from_job_document

logger = logging.getLogger(__name__)


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Infer and set job data provenance")
    parser.add_argument("--mongo-db", required=True)
    parser.add_argument("--apply", action="store_true", help="Write updates (default dry-run)")
    return parser.parse_args()


async def migrate(db_name: str, *, apply: bool) -> dict[str, int]:
    async with open_database(db_name) as database:
        await ensure_job_indexes(database)
        jobs = database["jobs"]
        by_provenance: dict[str, int] = {}
        ops: list[UpdateOne] = []
        scanned = 0
        async for doc in jobs.find({}):
            scanned += 1
            provenance = infer_provenance_from_job_document(doc)
            by_provenance[provenance.value] = by_provenance.get(provenance.value, 0) + 1
            current = doc.get("data_provenance")
            if current == provenance.value:
                continue
            ops.append(
                UpdateOne(
                    {"_id": doc["_id"]},
                    {"$set": {"data_provenance": provenance.value}},
                )
            )
        if not apply:
            return {
                "scanned": scanned,
                "would_update": len(ops),
                "updated": 0,
                "inferred_distribution": by_provenance,
            }
        updated = 0
        if ops:
            result = await jobs.bulk_write(ops, ordered=False)
            updated = result.modified_count
        return {
            "scanned": scanned,
            "would_update": len(ops),
            "updated": updated,
            "inferred_distribution": by_provenance,
        }


def main() -> None:
    settings = get_settings()
    configure_logging(settings)
    args = _parse_args()
    if args.mongo_db == settings.mongo_db_name and not settings.allow_collection_production_db:
        raise SystemExit("Refusing production DB without ALLOW_COLLECTION_PRODUCTION_DB=true")
    summary = asyncio.run(migrate(args.mongo_db, apply=args.apply))
    print(json.dumps(summary, indent=2))
    logger.info("Provenance migration apply=%s summary=%s", args.apply, summary)


if __name__ == "__main__":
    main()
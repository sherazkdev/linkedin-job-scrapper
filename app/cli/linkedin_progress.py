"""Report LinkedIn collection checkpoint progress (MongoDB, read-only)."""

import argparse
import asyncio
import json

from app.core.config import get_settings
from app.core.logging import configure_logging
from app.database.temp_database import open_database
from app.modules.jobs.models.job import JobSource


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="LinkedIn target checkpoint progress")
    parser.add_argument("--mongo-db", default=None)
    return parser.parse_args()


def _safe_db(settings, explicit: str | None) -> str:
    name = explicit or settings.celery_worker_mongo_db_name
    if (
        name == settings.mongo_db_name
        and not settings.allow_collection_production_db
        and not name.endswith("_test")
    ):
        name = f"{settings.mongo_db_name}_test"
    return name


async def _run(db_name: str) -> dict:
    async with open_database(db_name) as database:
        checkpoints = database["collection_checkpoints"]
        targets = database["collection_targets"]
        linkedin_checkpoints = await checkpoints.find(
            {"source": JobSource.LINKEDIN.value}
        ).to_list(length=5000)
        linkedin_targets = await targets.find(
            {"source": JobSource.LINKEDIN.value}
        ).to_list(length=5000)
        return {
            "database": db_name,
            "linkedin_checkpoints": len(linkedin_checkpoints),
            "linkedin_scheduler_targets": len(linkedin_targets),
            "checkpoints_sample": [
                {
                    "country_code": doc.get("country_code"),
                    "keyword": doc.get("keyword"),
                    "page_index": (doc.get("checkpoint") or {}).get("page_index"),
                    "processed_count": len((doc.get("checkpoint") or {}).get("processed_ids", [])),
                }
                for doc in linkedin_checkpoints[:25]
            ],
        }


def main() -> None:
    settings = get_settings()
    configure_logging(settings)
    args = _parse_args()
    db_name = _safe_db(settings, args.mongo_db)
    report = asyncio.run(_run(db_name))
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
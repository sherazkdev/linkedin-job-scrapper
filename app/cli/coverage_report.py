"""Print global coverage report (no secrets)."""

import argparse
import asyncio
import json
import sys

from app.core.config import get_settings
from app.core.logging import configure_logging
from app.database.collection_indexes import ensure_coverage_indexes
from app.database.temp_database import open_database
from app.modules.coverage.report import build_coverage_report


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Global coverage monitoring report")
    parser.add_argument("--mongo-db", default=None, help="MongoDB database name")
    return parser.parse_args()


def _resolve_db_name(settings, explicit: str | None) -> str:
    db_name = explicit or settings.celery_worker_mongo_db_name
    if (
        db_name == settings.mongo_db_name
        and not settings.allow_collection_production_db
        and not db_name.endswith("_test")
    ):
        db_name = f"{settings.mongo_db_name}_test"
    return db_name


async def _run(db_name: str) -> dict:
    async with open_database(db_name) as database:
        await ensure_coverage_indexes(database)
        return await build_coverage_report(database)


def main() -> None:
    settings = get_settings()
    configure_logging(settings)
    args = _parse_args()
    db_name = _resolve_db_name(settings, args.mongo_db)
    report = asyncio.run(_run(db_name))
    print(json.dumps(report, default=str, indent=2))


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        sys.exit(130)
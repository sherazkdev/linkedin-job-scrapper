"""Operational monitoring snapshot (no secrets)."""

import argparse
import asyncio
import json
import sys

from app.core.config import get_settings
from app.core.logging import configure_logging
from app.database.temp_database import open_database
from app.modules.operations.monitoring import build_operations_snapshot


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Collection and job-store monitoring")
    parser.add_argument(
        "--mongo-db",
        default=None,
        help="Database name (default: CELERY_WORKER_MONGO_DB_NAME or global_jobs_test)",
    )
    return parser.parse_args()


async def _run(db_name: str) -> dict:
    async with open_database(db_name) as database:
        return await build_operations_snapshot(database)


def main() -> None:
    settings = get_settings()
    configure_logging(settings)
    args = _parse_args()
    db_name = args.mongo_db or settings.celery_worker_mongo_db_name
    if (
        db_name == settings.mongo_db_name
        and not settings.allow_collection_production_db
        and not db_name.endswith("_test")
    ):
        db_name = f"{settings.mongo_db_name}_test"
    snapshot = asyncio.run(_run(db_name))
    print(json.dumps(snapshot, default=str, indent=2))


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        sys.exit(130)
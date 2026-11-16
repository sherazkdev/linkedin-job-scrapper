"""Sync pilot LinkedIn collection_targets from config (does not enable 2,000 manifest rows)."""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
from pathlib import Path

from app.core.config import get_settings
from app.core.logging import configure_logging
from app.database.temp_database import open_database
from app.modules.collection.repositories.target_repository import TargetRepository
from app.modules.jobs.models.job import JobSource

logger = logging.getLogger(__name__)

DEFAULT_CONFIG = (
    Path(__file__).resolve().parents[2] / "config" / "linkedin_pilot_targets.json"
)


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Upsert pilot LinkedIn scheduler targets")
    parser.add_argument(
        "--config",
        type=Path,
        default=DEFAULT_CONFIG,
        help="Pilot targets JSON (default: config/linkedin_pilot_targets.json)",
    )
    parser.add_argument(
        "--mongo-db",
        default=None,
        help="MongoDB database name (default: CELERY_WORKER_MONGO_DB_NAME)",
    )
    parser.add_argument(
        "--enable",
        action="store_true",
        help="Force enabled=true on all pilot rows from config",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print actions without writing",
    )
    return parser.parse_args()


async def _run(args: argparse.Namespace) -> int:
    settings = get_settings()
    db_name = args.mongo_db or settings.celery_worker_mongo_db_name
    with args.config.open(encoding="utf-8") as handle:
        payload = json.load(handle)
    rows = payload.get("targets")
    if not isinstance(rows, list):
        raise SystemExit("config must include targets array")

    upserted = 0
    async with open_database(db_name) as database:
        repo = TargetRepository(database)
        for row in rows:
            if not isinstance(row, dict):
                continue
            enabled = bool(row.get("enabled", False))
            if args.enable:
                enabled = True
            loc = row.get("search_location") or None
            if isinstance(loc, str) and not loc.strip():
                loc = None
            doc = {
                "source": JobSource.LINKEDIN.value,
                "country_code": str(row["country_code"]).upper(),
                "keyword": str(row["keyword"]).strip().lower(),
                "search_location": loc or "",
                "enabled": enabled,
                "priority": int(row.get("priority", 100)),
                "max_jobs_per_run": int(row.get("max_jobs_per_run", 5)),
            }
            if args.dry_run:
                logger.info("dry-run upsert %s", doc)
                upserted += 1
                continue
            await repo.upsert_target(
                source=JobSource.LINKEDIN,
                country_code=doc["country_code"],
                keyword=doc["keyword"],
                search_location=loc,
                enabled=enabled,
                priority=doc["priority"],
                max_jobs_per_run=doc["max_jobs_per_run"],
            )
            upserted += 1

    logger.info("Pilot targets synced count=%s db=%s", upserted, db_name)
    return 0


def main() -> None:
    settings = get_settings()
    configure_logging(settings)
    args = _parse_args()
    raise SystemExit(asyncio.run(_run(args)))


if __name__ == "__main__":
    main()
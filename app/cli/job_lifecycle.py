"""Operator CLI: public listing expiry and lifecycle previews."""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import uuid

from app.core.config import get_settings
from app.core.logging import configure_logging
from app.database.temp_database import open_database
from app.modules.jobs.services.lifecycle import JobLifecycleService

logger = logging.getLogger(__name__)


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Job lifecycle operations")
    sub = parser.add_subparsers(dest="command", required=True)
    expire = sub.add_parser("expire-public", help="Apply seven-day (configurable) public listing expiry")
    expire.add_argument("--mongo-db", default=None)
    expire.add_argument("--dry-run", action="store_true", default=True)
    expire.add_argument("--apply", action="store_true", help="Actually update documents")
    expire.add_argument("--source", default=None, help="Optional source filter (e.g. linkedin)")
    expire.add_argument("--limit", type=int, default=None)
    expire.add_argument("--max-age-days", type=int, default=None)
    return parser.parse_args()


async def _run(args: argparse.Namespace) -> int:
    settings = get_settings()
    db_name = args.mongo_db or settings.mongo_db_name
    max_age = args.max_age_days if args.max_age_days is not None else settings.job_public_listing_max_age_days
    limit = args.limit or settings.job_expiry_batch_size
    dry_run = not args.apply
    batch_id = uuid.uuid4().hex[:16]

    async with open_database(db_name) as database:
        service = JobLifecycleService(database)
        result = await service.apply_public_listing_expiry(
            max_age_days=max_age,
            source=args.source,
            dry_run=dry_run,
            limit=limit,
            batch_id=batch_id,
        )
    print(json.dumps({"db": db_name, **result}, indent=2, default=str))
    return 0


def main() -> None:
    settings = get_settings()
    configure_logging(settings)
    raise SystemExit(asyncio.run(_run(_parse_args())))


if __name__ == "__main__":
    main()
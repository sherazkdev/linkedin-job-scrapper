"""Recover a single collection target after interrupt or stale lock (no secrets)."""

import argparse
import asyncio
import json
import sys

from app.core.config import get_settings
from app.core.logging import configure_logging
from app.database.temp_database import open_database
from app.modules.collection.repositories.run_repository import RunRepository
from app.modules.collection.repositories.target_repository import TargetRepository, lock_is_active
from app.modules.collection.services.run_service import CollectionRunService
from app.modules.jobs.models.job import JobSource


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Reconcile orphaned runs and stale locks for one collection target",
    )
    parser.add_argument("--source", required=True, help="Job source (e.g. linkedin)")
    parser.add_argument("--country", required=True, help="ISO country code (e.g. PK)")
    parser.add_argument("--keyword", required=True, help="Search keyword")
    parser.add_argument(
        "--mongo-db",
        default=None,
        help="Database name (default: CELERY_WORKER_MONGO_DB_NAME or global_jobs_test)",
    )
    return parser.parse_args()


async def _recover(
    *,
    db_name: str,
    source: JobSource,
    country_code: str,
    keyword: str,
) -> dict:
    async with open_database(db_name) as database:
        targets = TargetRepository(database)
        runs = RunRepository(database)
        run_service = CollectionRunService(runs)

        target = await targets.find_target(
            source=source,
            country_code=country_code,
            keyword=keyword,
        )
        active = await run_service.get_running(
            source=source,
            country_code=country_code,
            keyword=keyword,
        )
        before_lock = None if target is None else target.get("lock_owner")
        cancelled_run_id = None
        if active is not None and not lock_is_active(target):
            if await run_service.cancel_active_run(
                active["run_id"],
                error_summary="manual_recovery",
            ):
                cancelled_run_id = active["run_id"]
        stale_lock_released = await targets.release_stale_lock(
            source=source,
            country_code=country_code,
            keyword=keyword,
        )
        target_after = await targets.find_target(
            source=source,
            country_code=country_code,
            keyword=keyword,
        )
        active_after = await run_service.get_running(
            source=source,
            country_code=country_code,
            keyword=keyword,
        )
        return {
            "source": source.value,
            "country_code": country_code.upper(),
            "keyword": keyword.strip().lower(),
            "before": {
                "lock_owner": before_lock,
                "locked_until": target.get("locked_until") if target else None,
                "active_run_id": None if active is None else active.get("run_id"),
            },
            "actions": {
                "cancelled_run_id": cancelled_run_id,
                "stale_lock_released": stale_lock_released,
            },
            "after": {
                "lock_owner": None if target_after is None else target_after.get("lock_owner"),
                "locked_until": None if target_after is None else target_after.get("locked_until"),
                "active_run_id": None if active_after is None else active_after.get("run_id"),
            },
        }


def main() -> int:
    settings = get_settings()
    configure_logging(settings)
    args = _parse_args()
    db_name = args.mongo_db or settings.celery_worker_mongo_db_name
    if (
        db_name == settings.mongo_db_name
        and not settings.allow_collection_production_db
        and not db_name.endswith("_test")
    ):
        print(
            f"Refusing production database '{db_name}'. "
            "Use --mongo-db global_jobs_test or an isolated test database.",
            file=sys.stderr,
        )
        return 2
    source = JobSource(args.source.strip().lower())
    result = asyncio.run(
        _recover(
            db_name=db_name,
            source=source,
            country_code=args.country,
            keyword=args.keyword,
        )
    )
    print(json.dumps(result, default=str, indent=2))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except KeyboardInterrupt:
        raise SystemExit(130) from None
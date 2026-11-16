"""Import canonical coverage manifest into coverage_targets (dry-run by default)."""

import argparse
import asyncio
import json
import sys
from pathlib import Path

from app.core.config import get_settings
from app.core.logging import configure_logging
from app.database.collection_indexes import ensure_coverage_indexes
from app.database.temp_database import open_database
from app.modules.coverage.audit import audit_manifest_against_scheduler
from app.modules.coverage.manifest import (
    default_manifest_path,
    iter_canonical_targets,
    load_manifest,
    validate_manifest,
)
from app.modules.coverage.repository import CoverageTargetRepository


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Import 40×50 canonical coverage targets")
    parser.add_argument(
        "--manifest",
        type=Path,
        default=None,
        help="Manifest JSON (default: config/global_jobs_40_countries_50_keywords_manifest.json)",
    )
    parser.add_argument(
        "--mongo-db",
        default=None,
        help="Database name (default: test/safe name unless ALLOW_COLLECTION_PRODUCTION_DB)",
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Write coverage_targets documents (default: dry-run only)",
    )
    parser.add_argument(
        "--audit-scheduler",
        action="store_true",
        help="Include read-only collection_targets audit in output",
    )
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


async def _run(args: argparse.Namespace) -> dict:
    manifest_path = args.manifest or default_manifest_path()
    data = load_manifest(manifest_path)
    meta = validate_manifest(data)
    rows = iter_canonical_targets(data)
    db_name = _resolve_db_name(get_settings(), args.mongo_db)
    async with open_database(db_name) as database:
        await ensure_coverage_indexes(database)
        repo = CoverageTargetRepository(database)
        import_stats = await repo.import_targets(
            rows,
            schema_version=int(meta.get("schema_version", 1)),
            apply=args.apply,
        )
        payload: dict = {
            "manifest_path": str(manifest_path),
            "manifest_validation": meta,
            "database": db_name,
            "apply": args.apply,
            "import": import_stats,
            "coverage_targets_total": await repo.count_all(),
            "coverage_targets_enabled": await repo.count_enabled(),
        }
        if args.audit_scheduler:
            payload["scheduler_audit"] = await audit_manifest_against_scheduler(database)
        return payload


def main() -> None:
    settings = get_settings()
    configure_logging(settings)
    args = _parse_args()
    result = asyncio.run(_run(args))
    print(json.dumps(result, default=str, indent=2))


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        sys.exit(130)
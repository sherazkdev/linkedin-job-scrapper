"""Pilot → production promotion CLI (dry-run by default; apply requires explicit env)."""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
from pathlib import Path

from app.core.config import Settings, get_settings
from app.core.logging import configure_logging
from app.database.temp_database import open_database
from app.modules.promotion.pilot_to_production import (
    analyze_promotion,
    apply_promotion,
    fetch_eligible,
    new_batch_id,
    rollback_batch,
    write_backup,
)

logger = logging.getLogger(__name__)

DEFAULT_BACKUP_DIR = Path("evidence/promotion_backups")


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Promote verified pilot jobs to production DB")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("preflight", help="Counts and safety checks (read-only)")
    sub.add_parser("dry-run", help="Analyze without writes")
    backup = sub.add_parser("backup", help="Export eligible pilot jobs JSON (no production write)")
    backup.add_argument("--out", type=Path, default=None)
    apply = sub.add_parser("apply", help="Promote eligible jobs (requires ALLOW_PILOT_TO_PRODUCTION_PROMOTION)")
    apply.add_argument("--backup", type=Path, default=None)
    rollback = sub.add_parser("rollback", help="Rollback a promotion batch in production")
    rollback.add_argument("--batch-id", required=True)
    rollback.add_argument("--backup", type=Path, default=None)
    return parser.parse_args()


def _pilot_db(settings: Settings) -> str:
    return settings.pilot_mongo_db_name


def _assert_promotion_allowed(settings: Settings) -> None:
    if not settings.allow_pilot_to_production_promotion:
        raise SystemExit(
            "Refused: set ALLOW_PILOT_TO_PRODUCTION_PROMOTION=true only after explicit approval"
        )
    if settings.allow_collection_production_db and _pilot_db(settings) == settings.mongo_db_name:
        raise SystemExit("Refused: pilot and production DB names must differ")


async def _run(args: argparse.Namespace) -> int:
    settings = get_settings()
    pilot_db_name = _pilot_db(settings)
    prod_db_name = settings.mongo_db_name

    async with open_database(pilot_db_name) as pilot, open_database(prod_db_name) as prod:
        if args.command in ("preflight", "dry-run"):
            report = await analyze_promotion(pilot, prod)
            report["pilot_db"] = pilot_db_name
            report["production_db"] = prod_db_name
            report["promotion_apply_allowed"] = settings.allow_pilot_to_production_promotion
            print(json.dumps(report, indent=2, default=str))
            return 0

        if args.command == "backup":
            batch_id = new_batch_id()
            docs = await fetch_eligible(pilot)
            out = args.out or DEFAULT_BACKUP_DIR / f"{batch_id}.json"
            path = await write_backup(docs, out, batch_id=batch_id)
            print(json.dumps({"batch_id": batch_id, "backup_path": str(path), "count": len(docs)}))
            return 0

        if args.command == "apply":
            _assert_promotion_allowed(settings)
            batch_id = new_batch_id()
            docs = await fetch_eligible(pilot)
            backup_path = args.backup or DEFAULT_BACKUP_DIR / f"{batch_id}.json"
            await write_backup(docs, backup_path, batch_id=batch_id)
            # Snapshot production baseline into backup metadata
            result = await apply_promotion(
                pilot_db=pilot,
                production_db=prod,
                batch_id=batch_id,
                docs=docs,
            )
            result["backup_path"] = str(backup_path)
            print(json.dumps(result, indent=2, default=str))
            return 0

        if args.command == "rollback":
            _assert_promotion_allowed(settings)
            result = await rollback_batch(prod, batch_id=args.batch_id, backup_path=args.backup)
            print(json.dumps(result, indent=2))
            return 0

    return 1


def main() -> None:
    settings = get_settings()
    configure_logging(settings)
    args = _parse_args()
    raise SystemExit(asyncio.run(_run(args)))


if __name__ == "__main__":
    main()
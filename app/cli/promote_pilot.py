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
from app.modules.promotion.monitoring import collect_publication_metrics
from app.modules.promotion.pilot_to_production import (
    PRODUCTION_DB_NAME,
    PILOT_DB_NAME,
    analyze_promotion,
    apply_promotion,
    assert_promotion_database_names,
    fetch_eligible,
    fetch_production_snapshots,
    new_batch_id,
    rollback_batch,
    validate_eligible_jobs,
    write_backup,
)
from app.modules.promotion.publication_sync import (
    analyze_publication_sync,
    apply_production_deprecations,
)
from app.modules.promotion.sync_lock import promotion_sync_lock

logger = logging.getLogger(__name__)

DEFAULT_BACKUP_DIR = Path("evidence/promotion_backups")


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Promote verified pilot jobs to production DB")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("preflight", help="Counts, DB names, validation (read-only)")
    sub.add_parser("dry-run", help="Analyze without writes")
    sub.add_parser("validate", help="Eligibility validation only")
    backup = sub.add_parser("backup", help="Pilot + production prior snapshot (no promotion)")
    backup.add_argument("--out", type=Path, default=None)
    apply = sub.add_parser("apply", help="Promote eligible jobs (requires ALLOW_PILOT_TO_PRODUCTION_PROMOTION)")
    apply.add_argument("--backup", type=Path, default=None)
    rollback = sub.add_parser("rollback", help="Rollback a promotion batch in production")
    rollback.add_argument("--batch-id", required=True)
    rollback.add_argument("--backup", type=Path, required=True)
    sub.add_parser(
        "reconcile",
        help="Pilot vs production sync plan (create/update/deprecate counts, no writes)",
    )
    sub.add_parser("monitor", help="Freshness, sync lag, collection failures (read-only)")
    dep = sub.add_parser(
        "deprecate-stale",
        help="Apply STALE to prod jobs not in pilot eligibility (requires ALLOW_…_PROMOTION)",
    )
    dep.add_argument("--dry-run", action="store_true", help="Print IDs only, no writes")
    sync = sub.add_parser(
        "sync-apply",
        help="Locked apply of eligible pilot jobs (requires ALLOW_…_PROMOTION; optional deprecate)",
    )
    sync.add_argument("--backup", type=Path, default=None)
    sync.add_argument(
        "--deprecate",
        action="store_true",
        help="Also apply safe deprecations from reconcile plan",
    )
    return parser.parse_args()


def _pilot_db(settings: Settings) -> str:
    return settings.pilot_mongo_db_name


def _prod_db(settings: Settings) -> str:
    return settings.promotion_target_mongo_db_name


def _assert_promotion_allowed(settings: Settings) -> None:
    if not settings.allow_pilot_to_production_promotion:
        raise SystemExit(
            "Refused: set ALLOW_PILOT_TO_PRODUCTION_PROMOTION=true only after explicit approval"
        )
    assert_promotion_database_names(pilot_db=_pilot_db(settings), production_db=_prod_db(settings))


async def _run(args: argparse.Namespace) -> int:
    settings = get_settings()
    pilot_db_name = _pilot_db(settings)
    prod_db_name = _prod_db(settings)
    assert_promotion_database_names(pilot_db=pilot_db_name, production_db=prod_db_name)

    async with open_database(pilot_db_name) as pilot, open_database(prod_db_name) as prod:
        if args.command == "validate":
            report = await validate_eligible_jobs(pilot)
            print(json.dumps(report, indent=2, default=str))
            return 0

        if args.command in ("preflight", "dry-run"):
            report = await analyze_promotion(pilot, prod, enforce_db_names=True)
            report["pilot_db"] = pilot_db_name
            report["production_db"] = prod_db_name
            report["db_names_ok"] = pilot_db_name == PILOT_DB_NAME and prod_db_name == PRODUCTION_DB_NAME
            report["promotion_apply_allowed"] = settings.allow_pilot_to_production_promotion
            print(json.dumps(report, indent=2, default=str))
            return 0

        if args.command == "backup":
            batch_id = new_batch_id()
            docs = await fetch_eligible(pilot)
            ids = [str(d["sourceJobId"]) for d in docs if d.get("sourceJobId")]
            prod_prior = await fetch_production_snapshots(prod, ids)
            out = args.out or DEFAULT_BACKUP_DIR / f"{batch_id}.json"
            path = await write_backup(
                docs,
                out,
                batch_id=batch_id,
                production_prior_docs=prod_prior,
                meta={"type": "pre_promotion_safety_backup"},
            )
            print(
                json.dumps(
                    {
                        "batch_id": batch_id,
                        "backup_path": str(path),
                        "pilot_count": len(docs),
                        "production_prior_count": len(prod_prior),
                    },
                    indent=2,
                )
            )
            return 0

        if args.command == "apply":
            _assert_promotion_allowed(settings)
            batch_id = new_batch_id()
            docs = await fetch_eligible(pilot)
            ids = [str(d["sourceJobId"]) for d in docs if d.get("sourceJobId")]
            prod_prior = await fetch_production_snapshots(prod, ids)
            backup_path = args.backup or DEFAULT_BACKUP_DIR / f"{batch_id}.json"
            await write_backup(
                docs,
                backup_path,
                batch_id=batch_id,
                production_prior_docs=prod_prior,
            )
            result = await apply_promotion(
                pilot_db=pilot,
                production_db=prod,
                batch_id=batch_id,
                docs=docs,
                enforce_db_names=True,
            )
            result["backup_path"] = str(backup_path)
            print(json.dumps(result, indent=2, default=str))
            return 0

        if args.command == "rollback":
            _assert_promotion_allowed(settings)
            if not args.backup.is_file():
                raise SystemExit(f"Backup file required for rollback: {args.backup}")
            result = await rollback_batch(
                prod, batch_id=args.batch_id, backup_path=args.backup
            )
            print(json.dumps(result, indent=2))
            return 0

        if args.command == "reconcile":
            report = await analyze_publication_sync(pilot, prod, enforce_db_names=True)
            report["pilot_db"] = pilot_db_name
            report["production_db"] = prod_db_name
            report["promotion_apply_allowed"] = settings.allow_pilot_to_production_promotion
            print(json.dumps(report, indent=2, default=str))
            return 0

        if args.command == "monitor":
            report = await collect_publication_metrics(pilot_db=pilot, production_db=prod)
            report["pilot_db"] = pilot_db_name
            report["production_db"] = prod_db_name
            print(json.dumps(report, indent=2, default=str))
            return 0

        if args.command == "deprecate-stale":
            plan = await analyze_publication_sync(pilot, prod, enforce_db_names=True)
            ids = plan.get("sync_plan", {}).get("would_deprecate_ids") or []
            if args.dry_run:
                print(
                    json.dumps(
                        {
                            "would_deprecate_count": len(ids),
                            "ids": ids,
                            "reasons": plan.get("sync_plan", {}).get("would_deprecate_reasons"),
                        },
                        indent=2,
                    )
                )
                return 0
            _assert_promotion_allowed(settings)
            try:
                with promotion_sync_lock():
                    batch_id = new_batch_id()
                    result = await apply_production_deprecations(
                        prod, source_job_ids=ids, batch_id=batch_id
                    )
            except BlockingIOError as exc:
                raise SystemExit(str(exc)) from exc
            print(json.dumps(result, indent=2, default=str))
            return 0

        if args.command == "sync-apply":
            _assert_promotion_allowed(settings)
            plan = await analyze_publication_sync(pilot, prod, enforce_db_names=True)
            validation = plan.get("validation") or {}
            if not validation.get("validation_ok", True):
                raise SystemExit("Refused sync-apply: pilot validation failed")
            docs = await fetch_eligible(pilot)
            if not docs:
                raise SystemExit("Refused sync-apply: no eligible pilot jobs")
            try:
                with promotion_sync_lock():
                    batch_id = new_batch_id()
                    ids = [str(d["sourceJobId"]) for d in docs if d.get("sourceJobId")]
                    prod_prior = await fetch_production_snapshots(prod, ids)
                    backup_path = args.backup or DEFAULT_BACKUP_DIR / f"{batch_id}.json"
                    await write_backup(
                        docs,
                        backup_path,
                        batch_id=batch_id,
                        production_prior_docs=prod_prior,
                        meta={"type": "sync_apply"},
                    )
                    apply_result = await apply_promotion(
                        pilot_db=pilot,
                        production_db=prod,
                        batch_id=batch_id,
                        docs=docs,
                        enforce_db_names=True,
                    )
                    apply_result["backup_path"] = str(backup_path)
                    dep_result = None
                    if args.deprecate:
                        dep_ids = plan.get("sync_plan", {}).get("would_deprecate_ids") or []
                        if dep_ids:
                            dep_batch = new_batch_id()
                            dep_result = await apply_production_deprecations(
                                prod, source_job_ids=dep_ids, batch_id=dep_batch
                            )
                    print(
                        json.dumps(
                            {
                                "batch_id": batch_id,
                                "apply": apply_result,
                                "deprecation": dep_result,
                            },
                            indent=2,
                            default=str,
                        )
                    )
            except BlockingIOError as exc:
                raise SystemExit(str(exc)) from exc
            return 0

    return 1


def main() -> None:
    settings = get_settings()
    configure_logging(settings)
    args = _parse_args()
    raise SystemExit(asyncio.run(_run(args)))


if __name__ == "__main__":
    main()
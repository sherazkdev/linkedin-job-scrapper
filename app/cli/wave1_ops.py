"""Wave 1 rollout operations (pilot DB only, max 40 LinkedIn targets)."""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import sys
from datetime import UTC, datetime
from pathlib import Path

from app.core.config import get_settings
from app.core.logging import configure_logging
from app.database.temp_database import open_database
from app.modules.collection.models.enums import CollectionRunStatus
from app.modules.collection.repositories.target_repository import TargetRepository
from app.modules.coverage.manifest import load_manifest
from app.modules.jobs.models.job import JobSource

logger = logging.getLogger(__name__)

WAVE1_KEYWORD = "software engineer"
WAVE1_MAX_TARGETS = 40
WAVE1_MAX_JOBS = 5
EVIDENCE_DIR = Path("evidence/wave1_observation")


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Wave 1 LinkedIn scheduler (pilot DB)")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("preflight", help="Verify pilot DB isolation and settings")
    enable = sub.add_parser("enable", help="Disable other LinkedIn targets; enable Wave 1 (40)")
    enable.add_argument("--mongo-db", default=None)
    disable = sub.add_parser("disable", help="Disable all LinkedIn collection_targets")
    disable.add_argument("--mongo-db", default=None)
    sub.add_parser("status", help="Observation snapshot JSON")
    return parser.parse_args()


def _expected_worker_db(settings) -> str:
    return settings.celery_worker_mongo_db_name


def _assert_pilot_db_only(settings) -> None:
    db = _expected_worker_db(settings)
    if db == settings.mongo_db_name and not settings.allow_collection_production_db:
        raise SystemExit(
            f"Refusing: worker DB '{db}' equals production API DB and "
            "ALLOW_COLLECTION_PRODUCTION_DB is false"
        )
    if db != "global_jobs_pilot":
        raise SystemExit(
            f"Refusing Wave 1: expected CELERY_WORKER_MONGO_DB_NAME=global_jobs_pilot, got {db}"
        )
    if settings.allow_collection_production_db:
        raise SystemExit("Refusing Wave 1: ALLOW_COLLECTION_PRODUCTION_DB must be false")


def _assert_scheduler_gates(settings) -> None:
    if not settings.celery_allow_linkedin_tasks:
        raise SystemExit("Preflight fail: CELERY_ALLOW_LINKEDIN_TASKS must be true")
    if settings.celery_dispatch_max_per_tick != 1:
        raise SystemExit("Preflight fail: CELERY_DISPATCH_MAX_PER_TICK must be 1")
    if settings.linkedin_max_live_runs_per_24h > 30:
        raise SystemExit("Preflight fail: LINKEDIN_MAX_LIVE_RUNS_PER_24H must be <= 30")


async def _mongo_counts(db_name: str, prod_db: str) -> dict:
    async with open_database(db_name) as pilot:
        pilot_jobs = await pilot["jobs"].count_documents({})
        pilot_li = await pilot["jobs"].count_documents({"source": JobSource.LINKEDIN.value})
        enabled = await pilot["collection_targets"].count_documents(
            {"source": JobSource.LINKEDIN.value, "enabled": True}
        )
    async with open_database(prod_db) as prod:
        prod_jobs = await prod["jobs"].count_documents({})
        prod_li_delta_note = "read_only_baseline"
    return {
        "pilot_db": db_name,
        "production_db": prod_db,
        "pilot_job_count": pilot_jobs,
        "pilot_linkedin_jobs": pilot_li,
        "production_job_count": prod_jobs,
        "linkedin_enabled_targets": enabled,
        "production_note": prod_li_delta_note,
    }


async def _preflight() -> int:
    settings = get_settings()
    _assert_pilot_db_only(settings)
    _assert_scheduler_gates(settings)
    counts = await _mongo_counts(_expected_worker_db(settings), settings.mongo_db_name)
    payload = {
        "ok": True,
        "wave": 1,
        "timestamp": datetime.now(UTC).isoformat(),
        "settings": {
            "celery_worker_mongo_db_name": settings.celery_worker_mongo_db_name,
            "mongo_db_name_api": settings.mongo_db_name,
            "allow_collection_production_db": settings.allow_collection_production_db,
            "allow_live_linkedin_collection": settings.allow_live_linkedin_collection,
            "celery_allow_linkedin_tasks": settings.celery_allow_linkedin_tasks,
            "linkedin_max_live_runs_per_24h": settings.linkedin_max_live_runs_per_24h,
            "dispatch_max_per_tick": settings.celery_dispatch_max_per_tick,
            "beat_interval_seconds": settings.celery_beat_dispatch_interval_seconds,
            "target_cooldown_seconds": settings.celery_target_cooldown_seconds,
        },
        "counts": counts,
    }
    payload["worker_live_collection"] = settings.allow_live_linkedin_collection
    print(json.dumps(payload, indent=2, default=str))
    return 0


def _manifest_country_codes() -> list[str]:
    manifest = load_manifest()
    codes = sorted(
        {str(c["country_code"]).upper() for c in manifest.get("countries", []) if isinstance(c, dict)}
    )
    if len(codes) != WAVE1_MAX_TARGETS:
        raise SystemExit(f"Expected {WAVE1_MAX_TARGETS} countries, manifest has {len(codes)}")
    return codes


async def _enable(db_name: str) -> int:
    settings = get_settings()
    _assert_pilot_db_only(settings)
    _assert_scheduler_gates(settings)
    if not settings.allow_live_linkedin_collection:
        raise SystemExit("Enable must run on worker-linkedin with ALLOW_LIVE_LINKEDIN_COLLECTION=true")
    countries = _manifest_country_codes()
    async with open_database(db_name) as database:
        disabled = await database["collection_targets"].update_many(
            {"source": JobSource.LINKEDIN.value},
            {"$set": {"enabled": False}},
        )
        repo = TargetRepository(database)
        for cc in countries:
            await repo.upsert_target(
                source=JobSource.LINKEDIN,
                country_code=cc,
                keyword=WAVE1_KEYWORD,
                search_location=None,
                enabled=True,
                priority=100,
                max_jobs_per_run=WAVE1_MAX_JOBS,
            )
        wave_filter = {
            "source": JobSource.LINKEDIN.value,
            "enabled": True,
            "keyword": WAVE1_KEYWORD,
            "search_location": "",
        }
        enabled = await database["collection_targets"].count_documents(wave_filter)
        enabled_codes = await database["collection_targets"].distinct("country_code", wave_filter)
    if enabled != WAVE1_MAX_TARGETS:
        missing = sorted(set(countries) - {str(c) for c in enabled_codes})
        raise SystemExit(
            f"After enable expected {WAVE1_MAX_TARGETS} enabled, got {enabled}; missing={missing}"
        )
    EVIDENCE_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(UTC)
    (EVIDENCE_DIR / "wave1_started_at.json").write_text(
        json.dumps(
            {
                "started_at": stamp.isoformat(),
                "observation_ends_at": (stamp.timestamp() + 86400),
                "disabled_previous": disabled.modified_count,
                "enabled_targets": enabled,
                "keyword": WAVE1_KEYWORD,
                "db": db_name,
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    print(
        json.dumps(
            {
                "ok": True,
                "enabled_targets": enabled,
                "disabled_previous_rows": disabled.modified_count,
                "countries": countries,
            }
        )
    )
    return 0


async def _disable(db_name: str) -> int:
    async with open_database(db_name) as database:
        result = await database["collection_targets"].update_many(
            {"source": JobSource.LINKEDIN.value},
            {"$set": {"enabled": False}},
        )
    print(json.dumps({"ok": True, "disabled_count": result.modified_count}))
    return 0


async def _status() -> int:
    settings = get_settings()
    db_name = _expected_worker_db(settings)
    since_file = EVIDENCE_DIR / "wave1_started_at.json"
    started_at = None
    if since_file.is_file():
        started_at = json.loads(since_file.read_text(encoding="utf-8")).get("started_at")
    since_dt = datetime.fromisoformat(started_at) if started_at else None
    async with open_database(db_name) as database:
        run_query: dict = {
            "source": JobSource.LINKEDIN.value,
            "dry_run": False,
        }
        if since_dt:
            run_query["started_at"] = {"$gte": since_dt}
        completed = await database["collection_runs"].count_documents(
            {**run_query, "status": CollectionRunStatus.COMPLETED.value}
        )
        failed = await database["collection_runs"].count_documents(
            {**run_query, "status": CollectionRunStatus.FAILED.value}
        )
        running = await database["collection_runs"].count_documents(
            {**run_query, "status": CollectionRunStatus.RUNNING.value}
        )
        countries = await database["collection_runs"].distinct("country_code", run_query)
        jobs = await database["jobs"].count_documents({"source": JobSource.LINKEDIN.value})
        enabled = await database["collection_targets"].count_documents(
            {"source": JobSource.LINKEDIN.value, "enabled": True}
        )
    prod_jobs = None
    async with open_database(settings.mongo_db_name) as prod:
        prod_jobs = await prod["jobs"].count_documents({})

    print(
        json.dumps(
            {
                "wave": 1,
                "observation_started_at": started_at,
                "pilot_linkedin_jobs_total": jobs,
                "production_jobs_total": prod_jobs,
                "runs_completed": completed,
                "runs_failed": failed,
                "runs_running": running,
                "countries_seen_in_runs": sorted([str(c) for c in countries if c]),
                "enabled_targets": enabled,
                "generated_at": datetime.now(UTC).isoformat(),
            },
            indent=2,
            default=str,
        )
    )
    return 0


async def _dispatch(args: argparse.Namespace) -> int:
    if args.command == "preflight":
        return await _preflight()
    if args.command == "enable":
        db = args.mongo_db or get_settings().celery_worker_mongo_db_name
        return await _enable(db)
    if args.command == "disable":
        db = args.mongo_db or get_settings().celery_worker_mongo_db_name
        return await _disable(db)
    if args.command == "status":
        return await _status()
    return 1


def main() -> None:
    settings = get_settings()
    configure_logging(settings)
    args = _parse_args()
    raise SystemExit(asyncio.run(_dispatch(args)))


if __name__ == "__main__":
    main()
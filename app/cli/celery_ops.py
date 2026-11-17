"""Operational helpers for Celery workers (no public exposure)."""

import argparse
import json
import logging
import sys
from uuid import uuid4

from app.core.config import get_settings
from app.core.logging import configure_logging
from app.workers.celery_app import celery_app
from app.workers.readiness import evaluate_worker_readiness
from app.workers.redis_urls import resolve_celery_broker_url

logger = logging.getLogger(__name__)


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Celery operational utilities")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("ping", help="Worker availability via Celery inspect ping")
    worker_ready = sub.add_parser(
        "worker-ready",
        help="Solo-safe readiness (ping, registered, or busy solo worker)",
    )
    worker_ready.add_argument("--timeout", type=float, default=8.0)
    sub.add_parser("stats", help="Queue depth and active tasks (sanitized)")
    inspect = sub.add_parser("inspect", help="Raw inspect snapshot (internal)")
    inspect.add_argument("action", choices=["active", "reserved", "scheduled", "stats"])
    sub.add_parser("dispatch-once", help="Run dispatcher once (fixture-eligible targets)")
    pilot = sub.add_parser(
        "pilot-dispatch-once",
        help="Enqueue exactly one collection task with a unique task_id (live pilots)",
    )
    pilot.add_argument("--source", default="linkedin")
    pilot.add_argument("--country-code", default="PK")
    pilot.add_argument("--keyword", default="junior erp consultant")
    pilot.add_argument("--search-location", default="islamabad, pakistan")
    pilot.add_argument("--max-jobs", type=int, default=1)
    return parser.parse_args()


def _queue_depth(broker_url: str, queue_name: str) -> int | None:
    try:
        from urllib.parse import urlparse

        import redis

        parsed = urlparse(broker_url)
        db = int(parsed.path.lstrip("/") or 0)
        client = redis.Redis(
            host=parsed.hostname or "localhost",
            port=parsed.port or 6379,
            password=parsed.password,
            db=db,
            socket_connect_timeout=3,
        )
        return client.llen(queue_name)
    except Exception as exc:
        logger.warning("Queue depth unavailable: %s", exc.__class__.__name__)
        return None


def main() -> None:
    settings = get_settings()
    configure_logging(settings)
    args = _parse_args()

    if args.command == "ping":
        inspector = celery_app.control.inspect(timeout=5.0)
        response = inspector.ping() if inspector else None
        ok = bool(response)
        print(json.dumps({"workers": list(response.keys()) if response else [], "ok": ok}))
        raise SystemExit(0 if ok else 1)

    if args.command == "worker-ready":
        timeout = max(float(args.timeout), 1.0)
        inspector = celery_app.control.inspect(timeout=timeout)
        ping = inspector.ping() if inspector else None
        registered = inspector.registered() if inspector else None
        active = inspector.active() if inspector else None
        result = evaluate_worker_readiness(
            ping=ping,
            registered=registered,
            active=active,
            pool="solo",
        )
        print(json.dumps(result))
        raise SystemExit(0 if result["ok"] else 1)

    if args.command == "stats":
        inspector = celery_app.control.inspect(timeout=5.0)
        active = inspector.active() if inspector else None
        broker = resolve_celery_broker_url(settings.redis_url, settings.celery_broker_url)
        depth = _queue_depth(broker, settings.celery_task_default_queue)
        active_count = sum(len(v) for v in active.values()) if active else 0
        print(
            json.dumps(
                {
                    "queue": settings.celery_task_default_queue,
                    "queue_depth": depth,
                    "active_task_count": active_count,
                    "worker_nodes": list(active.keys()) if active else [],
                }
            )
        )
        raise SystemExit(0)

    if args.command == "inspect":
        inspector = celery_app.control.inspect(timeout=5.0)
        method = getattr(inspector, args.action, None)
        if method is None:
            raise SystemExit(f"Unsupported inspect action: {args.action}")
        payload = method()
        print(json.dumps(payload or {}, default=str))
        raise SystemExit(0)

    if args.command == "dispatch-once":
        from app.workers.dispatcher import dispatch_eligible_sync

        summary = dispatch_eligible_sync()
        print(json.dumps(summary, default=str))
        raise SystemExit(0)

    if args.command == "pilot-dispatch-once":
        import asyncio

        from app.database.temp_database import open_database
        from app.modules.scheduling.linkedin_daily_cap import (
            assert_live_linkedin_daily_cap,
            live_linkedin_cap_enforced,
        )
        from app.workers.tasks import run_collection_task

        if args.source == "linkedin" and live_linkedin_cap_enforced(settings):

            async def _check_cap() -> None:
                db_name = settings.celery_worker_mongo_db_name
                async with open_database(db_name) as database:
                    await assert_live_linkedin_daily_cap(database, settings)

            try:
                asyncio.run(_check_cap())
            except Exception as exc:
                print(json.dumps({"ok": False, "error": str(exc)}))
                raise SystemExit(22) from exc

        suffix = uuid4().hex[:12]
        task_id = (
            f"pilot-{args.source}-{args.country_code}-{args.keyword.replace(' ', '_')}"
            f"-{suffix}"
        )
        run_collection_task.apply_async(
            kwargs={
                "source": args.source,
                "country_code": args.country_code,
                "keyword": args.keyword,
                "max_jobs": args.max_jobs,
                "search_location": args.search_location,
            },
            queue=settings.celery_task_default_queue,
            task_id=task_id,
        )
        print(
            json.dumps(
                {
                    "task_id": task_id,
                    "source": args.source,
                    "country_code": args.country_code,
                    "keyword": args.keyword,
                    "search_location": args.search_location,
                    "max_jobs": args.max_jobs,
                    "queue": settings.celery_task_default_queue,
                }
            )
        )
        raise SystemExit(0)

    raise SystemExit(2)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        sys.exit(130)

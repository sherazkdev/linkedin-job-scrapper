"""Operational helpers for Celery workers (no public exposure)."""

import argparse
import json
import logging
import sys

from app.core.config import get_settings
from app.core.logging import configure_logging
from app.workers.celery_app import celery_app
from app.workers.redis_urls import resolve_celery_broker_url

logger = logging.getLogger(__name__)


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Celery operational utilities")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("ping", help="Worker availability via Celery inspect ping")
    sub.add_parser("stats", help="Queue depth and active tasks (sanitized)")
    inspect = sub.add_parser("inspect", help="Raw inspect snapshot (internal)")
    inspect.add_argument("action", choices=["active", "reserved", "scheduled", "stats"])
    sub.add_parser("dispatch-once", help="Run dispatcher once (fixture-eligible targets)")
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

    raise SystemExit(2)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        sys.exit(130)

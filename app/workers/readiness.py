"""Celery worker readiness probes (solo-safe, bounded)."""

from __future__ import annotations

from typing import Any

SOLO_WORKER_PREFIX = "linkedin-worker@"


def evaluate_worker_readiness(
    *,
    ping: dict[str, Any] | None,
    registered: dict[str, list[str]] | None,
    active: dict[str, list[Any]] | None,
    pool: str = "solo",
) -> dict[str, Any]:
    """Classify worker availability without treating a busy solo worker as down.

    Solo pool workers often cannot answer ``inspect.ping`` while executing a task.
    """
    workers_ping = list((ping or {}).keys())
    if workers_ping:
        return {
            "ok": True,
            "busy": False,
            "method": "inspect_ping",
            "workers": workers_ping,
            "active_task_count": _active_count(active),
        }

    workers_reg = list((registered or {}).keys())
    if workers_reg:
        return {
            "ok": True,
            "busy": False,
            "method": "inspect_registered",
            "workers": workers_reg,
            "active_task_count": _active_count(active),
        }

    active_count = _active_count(active)
    busy_nodes = [
        name
        for name, tasks in (active or {}).items()
        if tasks and name.startswith(SOLO_WORKER_PREFIX)
    ]
    if pool == "solo" and active_count > 0 and busy_nodes:
        return {
            "ok": True,
            "busy": True,
            "method": "solo_executing_task",
            "workers": busy_nodes,
            "active_task_count": active_count,
        }

    return {
        "ok": False,
        "busy": False,
        "method": "unavailable",
        "workers": [],
        "active_task_count": active_count,
    }


def _active_count(active: dict[str, list[Any]] | None) -> int:
    if not active:
        return 0
    return sum(len(v) for v in active.values())
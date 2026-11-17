"""Staged rollout configuration and throughput estimates (offline)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from app.core.config import Settings

DEFAULT_WAVES_PATH = Path("config/linkedin_scheduling_waves.json")


def load_rollout_config(path: Path | None = None) -> dict[str, Any]:
    waves_path = path or DEFAULT_WAVES_PATH
    if not waves_path.is_file():
        raise FileNotFoundError(f"Missing rollout config: {waves_path}")
    return json.loads(waves_path.read_text(encoding="utf-8"))


def estimate_daily_throughput(settings: Settings, *, config: dict[str, Any] | None = None) -> dict[str, Any]:
    """Conservative scheduler capacity model (single worker, serial LinkedIn runs)."""
    cfg = config or load_rollout_config()
    m = cfg.get("measurements") or {}
    run_seconds = float(m.get("seconds_per_run_conservative_planning") or 60)
    beat_iv = float(settings.celery_beat_dispatch_interval_seconds)
    max_tick = max(int(settings.celery_dispatch_max_per_tick), 1)
    cooldown = max(int(settings.celery_target_cooldown_seconds), 0)
    concurrency = max(int(settings.celery_worker_concurrency), 1)

    dispatches_per_hour = (3600.0 / beat_iv) * max_tick
    completes_per_hour_serial = (3600.0 / run_seconds) * min(concurrency, 1)
    effective_runs_per_hour = min(dispatches_per_hour, completes_per_hour_serial)
    scheduler_runs_per_day = (3600.0 / beat_iv) * max_tick * 24
    worker_runs_per_day = (3600.0 / run_seconds) * min(concurrency, 1) * 24
    runs_per_day = min(scheduler_runs_per_day, worker_runs_per_day)
    max_runs_same_target_per_day = (
        (86400.0 / cooldown) * max_tick if cooldown > 0 else scheduler_runs_per_day
    )
    recommended_operational_runs_per_day = float(
        m.get("recommended_operational_runs_per_day") or min(runs_per_day, 40)
    )

    waves = cfg.get("waves") or []
    return {
        "assumptions": {
            "run_seconds": run_seconds,
            "beat_interval_seconds": beat_iv,
            "dispatch_max_per_tick": max_tick,
            "target_cooldown_seconds": cooldown,
            "worker_concurrency": concurrency,
            "linkedin_serial_per_worker": True,
        },
        "scheduler_dispatches_per_day": round(scheduler_runs_per_day, 1),
        "worker_capacity_runs_per_day": round(worker_runs_per_day, 1),
        "estimated_completed_runs_per_day": round(runs_per_day, 1),
        "max_runs_per_single_target_per_day": round(max_runs_same_target_per_day, 1),
        "recommended_operational_runs_per_day": recommended_operational_runs_per_day,
        "full_manifest_rotation_days_scheduler_ceiling": round(2000 / max(runs_per_day, 1), 1),
        "full_manifest_rotation_days_recommended_ops": round(
            2000 / max(recommended_operational_runs_per_day, 1),
            1,
        ),
        "configured_waves": [
            {
                "id": w.get("id"),
                "name": w.get("name"),
                "max_enabled_linkedin_targets": w.get("max_enabled_linkedin_targets"),
                "days_to_touch_all_enabled_once_recommended_ops": round(
                    float(w.get("max_enabled_linkedin_targets") or 0)
                    / max(recommended_operational_runs_per_day, 1),
                    1,
                ),
                "days_to_touch_all_enabled_once_scheduler_ceiling": round(
                    float(w.get("max_enabled_linkedin_targets") or 0) / max(runs_per_day, 1),
                    1,
                ),
            }
            for w in waves
        ],
    }


def scheduling_architecture_snapshot(settings: Settings) -> dict[str, Any]:
    return {
        "beat_task": "app.workers.tasks.dispatch_collection_targets",
        "beat_interval_seconds": settings.celery_beat_dispatch_interval_seconds,
        "dispatch_max_per_tick": settings.celery_dispatch_max_per_tick,
        "fair_country_coverage": settings.celery_dispatch_fair_country_coverage,
        "default_queue": settings.celery_task_default_queue,
        "worker_prefetch_multiplier": 1,
        "task_acks_late": True,
        "duplicate_dispatch_prevention": "deterministic Celery task_id per target; skip on apply_async collision",
        "gates": {
            "celery_allow_linkedin_tasks": settings.celery_allow_linkedin_tasks,
            "allow_live_linkedin_collection": settings.allow_live_linkedin_collection,
        },
        "linkedin_max_live_runs_per_24h": settings.linkedin_max_live_runs_per_24h,
    }
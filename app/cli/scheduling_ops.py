"""Offline scheduling rollout and capacity reporting (no Beat, no live scrape)."""

from __future__ import annotations

import argparse
import json

from app.core.config import get_settings
from app.modules.scheduling.rollout import (
    estimate_daily_throughput,
    load_rollout_config,
    scheduling_architecture_snapshot,
)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="LinkedIn scheduling rollout (read-only)")
    parser.add_argument(
        "--waves-path",
        default="config/linkedin_scheduling_waves.json",
        help="Path to wave configuration JSON",
    )
    args = parser.parse_args(argv)
    settings = get_settings()
    config = load_rollout_config()
    payload = {
        "architecture": scheduling_architecture_snapshot(settings),
        "throughput_estimate": estimate_daily_throughput(settings, config=config),
        "waves": config.get("waves"),
        "readiness_criteria": config.get("readiness_criteria"),
        "rollback_steps": config.get("rollback_steps"),
    }
    print(json.dumps(payload, indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
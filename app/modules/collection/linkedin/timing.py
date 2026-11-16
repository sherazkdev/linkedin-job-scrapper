"""Monotonic timing helpers for structured collection logs (no secrets)."""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import Any


def monotonic_ms() -> float:
    return time.monotonic() * 1000.0


def duration_ms(start_monotonic_ms: float) -> int:
    return max(0, int(monotonic_ms() - start_monotonic_ms))


@dataclass(slots=True)
class PhaseTimer:
    """Tracks monotonic start time for a named pipeline phase."""

    logger: logging.Logger
    phase: str
    _started_ms: float = field(default_factory=monotonic_ms)

    def elapsed_ms(self) -> int:
        return duration_ms(self._started_ms)

    def finish(self, *, event: str = "end", **fields: Any) -> int:
        ms = self.elapsed_ms()
        extra = " ".join(f"{k}={v}" for k, v in sorted(fields.items()))
        suffix = f" {extra}" if extra else ""
        self.logger.info(
            "linkedin_collect phase=%s event=%s duration_ms=%s%s",
            self.phase,
            event,
            ms,
            suffix,
        )
        return ms

    def log(self, *, event: str, **fields: Any) -> None:
        ms = self.elapsed_ms()
        extra = " ".join(f"{k}={v}" for k, v in sorted(fields.items()))
        suffix = f" {extra}" if extra else ""
        self.logger.info(
            "linkedin_collect phase=%s event=%s elapsed_ms=%s%s",
            self.phase,
            event,
            ms,
            suffix,
        )


def log_phase_start(logger: logging.Logger, phase: str, **fields: Any) -> PhaseTimer:
    extra = " ".join(f"{k}={v}" for k, v in sorted(fields.items()))
    suffix = f" {extra}" if extra else ""
    logger.info("linkedin_collect phase=%s event=start%s", phase, suffix)
    return PhaseTimer(logger=logger, phase=phase)
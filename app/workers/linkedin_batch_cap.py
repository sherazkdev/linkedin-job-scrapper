"""Resolve effective LinkedIn per-run batch size (safety defaults vs explicit trials)."""

from __future__ import annotations

from app.core.config import Settings


def resolve_linkedin_max_jobs_per_run(
    configured: int,
    settings: Settings,
    *,
    allow_live: bool | None = None,
) -> int:
    """
    Hard cap always applies. Default soft cap (LINKEDIN_MAX_LIVE_JOBS_PER_RUN=5) applies
    unless LINKEDIN_HONOR_TARGET_BATCH_SIZES=true (explicit trial on worker/container).
    """
    hard = settings.linkedin_max_jobs_per_run_hard_cap
    cap = max(1, min(int(configured), hard, 500))
    live = settings.allow_live_linkedin_collection if allow_live is None else allow_live
    if not live:
        return cap
    if settings.linkedin_honor_target_batch_sizes:
        return cap
    return min(cap, settings.linkedin_max_live_jobs_per_run)
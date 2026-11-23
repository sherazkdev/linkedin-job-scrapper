"""Guards for scheduled pilot→production lifecycle (expiry) propagation."""

from __future__ import annotations

from typing import Any


def assess_deprecation_plan(
    sync_plan: dict[str, Any],
    *,
    production_published_count: int,
    mass_deprecate_ratio: float = 0.5,
    mass_deprecate_min_count: int = 25,
) -> dict[str, Any]:
    """
    Block unattended mass unpublish (e.g. first 7-day expiry wave on legacy catalog).
    Does not block zero deprecations or small incremental lifecycle updates.
    """
    would = int(sync_plan.get("would_deprecate_count") or 0)
    reasons = sync_plan.get("would_deprecate_reasons") or []
    expired_reasons = sum(
        1
        for row in reasons
        if str(row.get("reason") or "").startswith("pilot_status_expired")
    )
    ratio = (would / production_published_count) if production_published_count > 0 else 0.0
    mass_risk = would >= mass_deprecate_min_count and ratio >= mass_deprecate_ratio
    return {
        "would_deprecate_count": would,
        "production_published_count": production_published_count,
        "deprecate_ratio": round(ratio, 4),
        "expired_pilot_reasons": expired_reasons,
        "mass_deprecate_risk": mass_risk,
        "requires_explicit_mass_approval": mass_risk,
    }
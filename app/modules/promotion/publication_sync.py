"""Plan and apply pilot → production sync beyond one-shot promotion (read-only planners + gated apply)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

from pymongo.asynchronous.database import AsyncDatabase

from app.database.indexes import JOBS_COLLECTION
from app.modules.jobs.models.job import JobDataProvenance, JobSource, JobStatus
from app.modules.promotion.pilot_to_production import (
    ELIGIBLE_QUERY,
    PROMOTION_AUDIT_COLLECTION,
    analyze_promotion,
    fetch_eligible,
)

_DEPRECATION_PILOT_STATUSES = frozenset(
    {
        JobStatus.STALE.value,
        JobStatus.CLOSED.value,
        JobStatus.EXPIRED.value,
    }
)

PRODUCTION_PUBLISHED_QUERY = {
    **ELIGIBLE_QUERY,
}


def _source_job_id(doc: dict[str, Any]) -> str:
    return str(doc.get("sourceJobId") or "")


async def fetch_production_published(
    production_db: AsyncDatabase[Any],
) -> list[dict[str, Any]]:
    cursor = production_db[JOBS_COLLECTION].find(PRODUCTION_PUBLISHED_QUERY)
    return await cursor.to_list(length=50_000)


async def _pilot_deprecation_reason(
    pilot_db: AsyncDatabase[Any],
    source_job_id: str,
) -> str | None:
    """Return deprecate reason only for genuine pilot retraction — not collection/auth pauses."""
    doc = await pilot_db[JOBS_COLLECTION].find_one(
        {"source": JobSource.LINKEDIN.value, "sourceJobId": source_job_id}
    )
    if doc is None:
        return "pilot_row_removed"
    prov = doc.get("data_provenance")
    if prov != JobDataProvenance.LIVE_API_VERIFIED.value:
        return "pilot_not_live_verified"
    status = str(doc.get("status") or "")
    if status in _DEPRECATION_PILOT_STATUSES:
        return f"pilot_status_{status}"
    # Pilot row still active live-verified but temporarily not in ELIGIBLE_QUERY (e.g. validation).
    return None


async def resolve_deprecation_candidates(
    pilot_db: AsyncDatabase[Any],
    production_ids: set[str],
    eligible_pilot_ids: set[str],
) -> tuple[list[str], list[dict[str, Any]]]:
    """Production jobs not in pilot eligibility — deprecate only with explicit pilot retract."""
    missing_from_eligible = production_ids - eligible_pilot_ids
    ids: list[str] = []
    reasons: list[dict[str, Any]] = []
    for sid in sorted(missing_from_eligible):
        reason = await _pilot_deprecation_reason(pilot_db, sid)
        if reason:
            ids.append(sid)
            reasons.append({"sourceJobId": sid, "reason": reason})
    return ids, reasons


async def analyze_publication_sync(
    pilot_db: AsyncDatabase[Any],
    production_db: AsyncDatabase[Any],
    *,
    enforce_db_names: bool = True,
) -> dict[str, Any]:
    """Diff pilot eligibility vs production publication (no writes)."""
    promo = await analyze_promotion(pilot_db, production_db, enforce_db_names=enforce_db_names)
    pilot_docs = await fetch_eligible(pilot_db)
    prod_docs = await fetch_production_published(production_db)
    pilot_ids = {_source_job_id(d) for d in pilot_docs if _source_job_id(d)}
    prod_ids = {_source_job_id(d) for d in prod_docs if _source_job_id(d)}

    would_deprecate_ids, deprecate_reasons = await resolve_deprecation_candidates(
        pilot_db, prod_ids, pilot_ids
    )
    pilot_only_ids = sorted(pilot_ids - prod_ids)
    in_both = pilot_ids & prod_ids

    # Publication lag: pilot ahead of production on last_seen_at
    lag_samples: list[dict[str, Any]] = []
    prod_by_id = {_source_job_id(d): d for d in prod_docs}
    pilot_by_id = {_source_job_id(d): d for d in pilot_docs}
    for sid in sorted(in_both)[:20]:
        p = pilot_by_id.get(sid) or {}
        r = prod_by_id.get(sid) or {}
        pls = p.get("last_seen_at")
        rls = r.get("last_seen_at")
        if isinstance(pls, datetime) and isinstance(rls, datetime):
            if pls.tzinfo is None:
                pls = pls.replace(tzinfo=UTC)
            if rls.tzinfo is None:
                rls = rls.replace(tzinfo=UTC)
            delta = (pls - rls).total_seconds()
            if delta > 60:
                lag_samples.append(
                    {
                        "sourceJobId": sid,
                        "pilot_last_seen_at": pls.isoformat(),
                        "production_last_seen_at": rls.isoformat(),
                        "lag_seconds": int(delta),
                    }
                )

    return {
        **promo,
        "sync_plan": {
            "pilot_eligible_count": len(pilot_ids),
            "production_published_count": len(prod_ids),
            "would_create_ids": pilot_only_ids,
            "would_create_count": len(pilot_only_ids),
            "would_update_count": len(in_both),
            "would_deprecate_ids": would_deprecate_ids,
            "would_deprecate_count": len(would_deprecate_ids),
            "would_deprecate_reasons": deprecate_reasons,
            "would_retain_despite_not_eligible": sorted(
                (prod_ids - pilot_ids) - set(would_deprecate_ids)
            ),
            "publication_lag_samples": lag_samples,
        },
    }


async def apply_production_deprecations(
    production_db: AsyncDatabase[Any],
    *,
    source_job_ids: list[str],
    batch_id: str,
    reason: str = "pilot_no_longer_eligible",
) -> dict[str, Any]:
    """Mark production LinkedIn jobs stale when pilot no longer lists them as eligible."""
    if not source_job_ids:
        return {"batch_id": batch_id, "deprecated_count": 0, "deprecated_ids": []}
    now = datetime.now(UTC)
    deprecated: list[str] = []
    for sid in source_job_ids:
        result = await production_db[JOBS_COLLECTION].update_one(
            {
                "source": JobSource.LINKEDIN.value,
                "sourceJobId": sid,
                "status": JobStatus.ACTIVE.value,
                "data_provenance": JobDataProvenance.LIVE_API_VERIFIED.value,
            },
            {
                "$set": {
                    "status": JobStatus.STALE.value,
                    "unpublished_at": now,
                    "unpublish_reason": reason,
                    "deprecation_batch_id": batch_id,
                }
            },
        )
        if result.modified_count:
            deprecated.append(sid)
    await production_db[PROMOTION_AUDIT_COLLECTION].insert_one(
        {
            "batch_id": batch_id,
            "created_at": now,
            "type": "deprecation",
            "deprecated_count": len(deprecated),
            "deprecated_ids": deprecated,
            "reason": reason,
        }
    )
    return {
        "batch_id": batch_id,
        "deprecated_count": len(deprecated),
        "deprecated_ids": deprecated,
    }
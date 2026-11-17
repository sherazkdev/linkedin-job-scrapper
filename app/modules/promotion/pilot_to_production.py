"""Idempotent pilot → production job promotion with audit trail."""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any
from uuid import uuid4

from pymongo.asynchronous.database import AsyncDatabase

from app.database.indexes import JOBS_COLLECTION
from app.modules.jobs.models.job import JobDataProvenance, JobSource, JobStatus

PROMOTION_AUDIT_COLLECTION = "promotion_audit_batches"
PILOT_DB_NAME = "global_jobs_pilot"
PRODUCTION_DB_NAME = "global_jobs"

ELIGIBLE_QUERY = {
    "source": JobSource.LINKEDIN.value,
    "data_provenance": JobDataProvenance.LIVE_API_VERIFIED.value,
    "status": JobStatus.ACTIVE.value,
    "sourceJobId": {"$exists": True, "$ne": ""},
    "job_url": {"$exists": True, "$ne": ""},
}

_PROMOTION_META_FIELDS = frozenset({"promotion_batch_id", "promoted_from_pilot_at"})


def _sanitize_for_export(doc: dict[str, Any]) -> dict[str, Any]:
    out = dict(doc)
    out.pop("_id", None)
    return out


def assert_promotion_database_names(*, pilot_db: str, production_db: str) -> None:
    if pilot_db != PILOT_DB_NAME:
        raise ValueError(f"pilot DB must be {PILOT_DB_NAME}, got {pilot_db}")
    if production_db != PRODUCTION_DB_NAME:
        raise ValueError(f"production DB must be {PRODUCTION_DB_NAME}, got {production_db}")


async def count_eligible(pilot_db: AsyncDatabase[Any]) -> int:
    return await pilot_db[JOBS_COLLECTION].count_documents(ELIGIBLE_QUERY)


async def fetch_eligible(
    pilot_db: AsyncDatabase[Any], *, limit: int | None = None
) -> list[dict[str, Any]]:
    cursor = pilot_db[JOBS_COLLECTION].find(ELIGIBLE_QUERY).sort("last_seen_at", -1)
    if limit:
        cursor = cursor.limit(limit)
    return await cursor.to_list(length=limit or 10_000)


async def fetch_production_snapshots(
    production_db: AsyncDatabase[Any],
    source_job_ids: list[str],
) -> list[dict[str, Any]]:
    if not source_job_ids:
        return []
    cursor = production_db[JOBS_COLLECTION].find(
        {
            "source": JobSource.LINKEDIN.value,
            "sourceJobId": {"$in": source_job_ids},
        }
    )
    return [_sanitize_for_export(d) for d in await cursor.to_list(length=len(source_job_ids) + 1)]


async def validate_eligible_jobs(
    pilot_db: AsyncDatabase[Any],
    *,
    max_posted_age_days: int = 30,
) -> dict[str, Any]:
    docs = await fetch_eligible(pilot_db)
    ids: list[str] = []
    issues: list[str] = []
    cutoff = datetime.now(UTC) - timedelta(days=max_posted_age_days)
    unique_ids: set[str] = set()
    duplicate_source_ids: list[str] = []
    for doc in docs:
        sid = str(doc.get("sourceJobId") or "")
        if sid in unique_ids:
            duplicate_source_ids.append(sid)
        unique_ids.add(sid)
        ids.append(sid)
        if doc.get("data_provenance") != JobDataProvenance.LIVE_API_VERIFIED.value:
            issues.append(f"{sid}: bad_provenance")
        if doc.get("status") != JobStatus.ACTIVE.value:
            issues.append(f"{sid}: not_active")
        url = str(doc.get("job_url") or "")
        if "linkedin.com" not in url.lower():
            issues.append(f"{sid}: job_url_not_linkedin")
        posted = doc.get("posted_at")
        if isinstance(posted, datetime) and posted.tzinfo is None:
            posted = posted.replace(tzinfo=UTC)
        if isinstance(posted, datetime) and posted < cutoff:
            issues.append(f"{sid}: posted_at_stale")
    return {
        "eligible_count": len(docs),
        "unique_source_job_ids": len(unique_ids),
        "duplicate_source_job_ids": duplicate_source_ids,
        "validation_issues": issues,
        "validation_ok": not duplicate_source_ids and not issues,
    }


async def analyze_promotion(
    pilot_db: AsyncDatabase[Any],
    production_db: AsyncDatabase[Any],
    *,
    enforce_db_names: bool = False,
) -> dict[str, Any]:
    if enforce_db_names:
        assert_promotion_database_names(pilot_db=pilot_db.name, production_db=production_db.name)
    eligible = await count_eligible(pilot_db)
    pilot_total = await pilot_db[JOBS_COLLECTION].count_documents({"source": JobSource.LINKEDIN.value})
    prod_total = await production_db[JOBS_COLLECTION].count_documents({})
    prod_linkedin = await production_db[JOBS_COLLECTION].count_documents(
        {"source": JobSource.LINKEDIN.value}
    )
    would_create = 0
    would_update = 0
    sample: list[dict[str, Any]] = []
    validation = await validate_eligible_jobs(pilot_db)
    docs = await fetch_eligible(pilot_db)
    for doc in docs:
        existing = await production_db[JOBS_COLLECTION].find_one(
            {"source": doc["source"], "sourceJobId": doc["sourceJobId"]},
            projection={"_id": 1},
        )
        if existing:
            would_update += 1
        else:
            would_create += 1
        if len(sample) < 5:
            sample.append(
                {
                    "sourceJobId": doc.get("sourceJobId"),
                    "search_country_code": doc.get("search_country_code"),
                    "country_code": doc.get("country_code"),
                    "posted_at": str(doc.get("posted_at")),
                    "job_url": doc.get("job_url"),
                    "data_provenance": doc.get("data_provenance"),
                }
            )
    return {
        "eligible_live_verified": eligible,
        "pilot_linkedin_total": pilot_total,
        "production_jobs_total": prod_total,
        "production_linkedin_total": prod_linkedin,
        "dry_run_would_create": would_create,
        "dry_run_would_update": would_update,
        "validation": validation,
        "sample_eligible": sample,
    }


async def write_backup(
    pilot_docs: list[dict[str, Any]],
    path: Path,
    *,
    batch_id: str,
    production_prior_docs: list[dict[str, Any]] | None = None,
    meta: dict[str, Any] | None = None,
) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload: dict[str, Any] = {
        "batch_id": batch_id,
        "created_at": datetime.now(UTC).isoformat(),
        "pilot_db": PILOT_DB_NAME,
        "production_db": PRODUCTION_DB_NAME,
        "pilot_document_count": len(pilot_docs),
        "production_prior_document_count": len(production_prior_docs or []),
        "pilot_documents": [_sanitize_for_export(d) for d in pilot_docs],
        "production_prior_documents": production_prior_docs or [],
        "meta": meta or {},
    }
    path.write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")
    return path


def _prior_production_from_backup(backup_path: Path, source_job_id: str) -> dict[str, Any] | None:
    if not backup_path.is_file():
        return None
    backup = json.loads(backup_path.read_text(encoding="utf-8"))
    for doc in backup.get("production_prior_documents") or []:
        if doc.get("sourceJobId") == source_job_id:
            return doc
    for doc in backup.get("documents") or []:
        if doc.get("sourceJobId") == source_job_id:
            return doc
    return None


async def apply_promotion(
    *,
    pilot_db: AsyncDatabase[Any],
    production_db: AsyncDatabase[Any],
    batch_id: str,
    docs: list[dict[str, Any]],
    enforce_db_names: bool = False,
) -> dict[str, Any]:
    if enforce_db_names:
        assert_promotion_database_names(pilot_db=pilot_db.name, production_db=production_db.name)
    created = 0
    updated = 0
    errors: list[str] = []
    entries: list[dict[str, Any]] = []
    now = datetime.now(UTC)
    for doc in docs:
        source_job_id = doc.get("sourceJobId")
        if not source_job_id:
            errors.append("missing_sourceJobId")
            continue
        filter_doc = {"source": doc["source"], "sourceJobId": source_job_id}
        existing = await production_db[JOBS_COLLECTION].find_one(filter_doc)
        export_doc = _sanitize_for_export(doc)
        export_doc["promoted_from_pilot_at"] = now
        export_doc["promotion_batch_id"] = batch_id
        try:
            if existing:
                prior_snapshot = _sanitize_for_export(existing)
                await production_db[JOBS_COLLECTION].update_one(
                    filter_doc,
                    {
                        "$set": {
                            k: v
                            for k, v in export_doc.items()
                            if k not in {"first_seen_at", "source", "sourceJobId"}
                        }
                    },
                )
                updated += 1
                entries.append(
                    {
                        "sourceJobId": source_job_id,
                        "outcome": "updated",
                        "prior_production_id": str(existing["_id"]),
                        "prior_production_document": prior_snapshot,
                    }
                )
            else:
                insert_doc = {**export_doc, "first_seen_at": doc.get("first_seen_at") or now}
                result = await production_db[JOBS_COLLECTION].insert_one(insert_doc)
                created += 1
                entries.append(
                    {
                        "sourceJobId": source_job_id,
                        "outcome": "created",
                        "production_id": str(result.inserted_id),
                    }
                )
        except Exception as exc:
            errors.append(f"{source_job_id}: {exc.__class__.__name__}")
    await production_db[PROMOTION_AUDIT_COLLECTION].insert_one(
        {
            "batch_id": batch_id,
            "created_at": now,
            "source_pilot_db": PILOT_DB_NAME,
            "target_production_db": PRODUCTION_DB_NAME,
            "created_count": created,
            "updated_count": updated,
            "errors": errors,
            "entries": entries,
        }
    )
    return {
        "batch_id": batch_id,
        "created": created,
        "updated": updated,
        "errors": errors,
        "failed_count": len(errors),
    }


async def _restore_production_document(
    production_db: AsyncDatabase[Any],
    *,
    source_job_id: str,
    prior: dict[str, Any],
) -> None:
    filter_doc = {"source": JobSource.LINKEDIN.value, "sourceJobId": source_job_id}
    prior_clean = {
        k: v
        for k, v in prior.items()
        if k not in {"_id", *_PROMOTION_META_FIELDS}
    }
    existing = await production_db[JOBS_COLLECTION].find_one(filter_doc)
    if existing is None:
        await production_db[JOBS_COLLECTION].insert_one(
            {**prior_clean, "source": JobSource.LINKEDIN.value, "sourceJobId": source_job_id}
        )
        return
    merged = {**prior_clean, "source": JobSource.LINKEDIN.value, "sourceJobId": source_job_id}
    await production_db[JOBS_COLLECTION].replace_one(filter_doc, merged, upsert=False)


async def rollback_batch(
    production_db: AsyncDatabase[Any],
    *,
    batch_id: str,
    backup_path: Path | None,
) -> dict[str, Any]:
    audit = await production_db[PROMOTION_AUDIT_COLLECTION].find_one({"batch_id": batch_id})
    if audit is None:
        raise ValueError(f"No audit batch {batch_id}")
    removed = 0
    restored = 0
    skipped = 0
    for entry in audit.get("entries") or []:
        source_job_id = entry.get("sourceJobId")
        if not source_job_id:
            skipped += 1
            continue
        if entry.get("outcome") == "created":
            result = await production_db[JOBS_COLLECTION].delete_one(
                {
                    "source": JobSource.LINKEDIN.value,
                    "sourceJobId": source_job_id,
                    "promotion_batch_id": batch_id,
                }
            )
            if result.deleted_count:
                removed += 1
        elif entry.get("outcome") == "updated":
            prior = entry.get("prior_production_document")
            if not prior and backup_path:
                prior = _prior_production_from_backup(backup_path, source_job_id)
            if prior:
                await _restore_production_document(
                    production_db, source_job_id=source_job_id, prior=prior
                )
                restored += 1
            else:
                skipped += 1
    return {
        "batch_id": batch_id,
        "removed_created": removed,
        "restored_updated": restored,
        "skipped": skipped,
    }


def new_batch_id() -> str:
    return f"pilot-promo-{datetime.now(UTC).strftime('%Y%m%dT%H%M%SZ')}-{uuid4().hex[:8]}"
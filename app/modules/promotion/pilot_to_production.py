"""Idempotent pilot → production job promotion with audit trail."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

from pymongo.asynchronous.database import AsyncDatabase

from app.database.indexes import JOBS_COLLECTION
from app.modules.jobs.models.job import JobDataProvenance, JobSource, JobStatus

PROMOTION_AUDIT_COLLECTION = "promotion_audit_batches"
ELIGIBLE_QUERY = {
    "source": JobSource.LINKEDIN.value,
    "data_provenance": JobDataProvenance.LIVE_API_VERIFIED.value,
    "status": JobStatus.ACTIVE.value,
    "sourceJobId": {"$exists": True, "$ne": ""},
    "job_url": {"$exists": True, "$ne": ""},
}


def _sanitize_for_export(doc: dict[str, Any]) -> dict[str, Any]:
    out = dict(doc)
    out.pop("_id", None)
    return out


async def count_eligible(pilot_db: AsyncDatabase[Any]) -> int:
    return await pilot_db[JOBS_COLLECTION].count_documents(ELIGIBLE_QUERY)


async def fetch_eligible(
    pilot_db: AsyncDatabase[Any], *, limit: int | None = None
) -> list[dict[str, Any]]:
    cursor = pilot_db[JOBS_COLLECTION].find(ELIGIBLE_QUERY).sort("last_seen_at", -1)
    if limit:
        cursor = cursor.limit(limit)
    return await cursor.to_list(length=limit or 10_000)


async def analyze_promotion(
    pilot_db: AsyncDatabase[Any],
    production_db: AsyncDatabase[Any],
) -> dict[str, Any]:
    eligible = await count_eligible(pilot_db)
    pilot_total = await pilot_db[JOBS_COLLECTION].count_documents({"source": JobSource.LINKEDIN.value})
    prod_total = await production_db[JOBS_COLLECTION].count_documents({})
    prod_linkedin = await production_db[JOBS_COLLECTION].count_documents(
        {"source": JobSource.LINKEDIN.value}
    )
    would_create = 0
    would_update = 0
    sample: list[dict[str, Any]] = []
    docs = await fetch_eligible(pilot_db, limit=500)
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
        "sample_eligible": sample,
    }


async def write_backup(docs: list[dict[str, Any]], path: Path, *, batch_id: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "batch_id": batch_id,
        "created_at": datetime.now(UTC).isoformat(),
        "document_count": len(docs),
        "documents": [_sanitize_for_export(d) for d in docs],
    }
    path.write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")
    return path


async def apply_promotion(
    *,
    pilot_db: AsyncDatabase[Any],
    production_db: AsyncDatabase[Any],
    batch_id: str,
    docs: list[dict[str, Any]],
) -> dict[str, Any]:
    created = 0
    updated = 0
    errors: list[str] = []
    entries: list[dict[str, Any]] = []
    now = datetime.now(UTC)
    for doc in docs:
        source_job_id = doc.get("sourceJobId")
        if not source_job_id:
            continue
        filter_doc = {"source": doc["source"], "sourceJobId": source_job_id}
        existing = await production_db[JOBS_COLLECTION].find_one(filter_doc)
        export_doc = _sanitize_for_export(doc)
        export_doc["promoted_from_pilot_at"] = now
        export_doc["promotion_batch_id"] = batch_id
        export_doc.pop("_id", None)
        try:
            if existing:
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
            "source_pilot_db": "global_jobs_pilot",
            "target_production_db": "global_jobs",
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
    }


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
    for entry in audit.get("entries") or []:
        if entry.get("outcome") == "created":
            await production_db[JOBS_COLLECTION].delete_one(
                {
                    "source": JobSource.LINKEDIN.value,
                    "sourceJobId": entry["sourceJobId"],
                    "promotion_batch_id": batch_id,
                }
            )
            removed += 1
        elif entry.get("outcome") == "updated" and backup_path and backup_path.is_file():
            backup = json.loads(backup_path.read_text(encoding="utf-8"))
            prior = next(
                (
                    d
                    for d in backup.get("documents") or []
                    if d.get("sourceJobId") == entry.get("sourceJobId")
                ),
                None,
            )
            if prior:
                await production_db[JOBS_COLLECTION].update_one(
                    {"source": JobSource.LINKEDIN.value, "sourceJobId": entry["sourceJobId"]},
                    {
                        "$set": {
                            k: v
                            for k, v in prior.items()
                            if k not in {"_id", "promotion_batch_id", "promoted_from_pilot_at"}
                        },
                        "$unset": {"promotion_batch_id": "", "promoted_from_pilot_at": ""},
                    },
                )
                restored += 1
    return {"batch_id": batch_id, "removed_created": removed, "restored_updated": restored}


def new_batch_id() -> str:
    return f"pilot-promo-{datetime.now(UTC).strftime('%Y%m%dT%H%M%SZ')}-{uuid4().hex[:8]}"
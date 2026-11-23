"""Job lifecycle helpers (stale, public listing expiry)."""

from datetime import UTC, datetime, timedelta
from typing import Any

from pymongo.asynchronous.database import AsyncDatabase

from app.database.indexes import JOBS_COLLECTION
from app.modules.jobs.models.job import JobStatus
from app.modules.jobs.public_visibility import effective_public_listing_date


class JobLifecycleService:
    def __init__(self, database: AsyncDatabase[Any]) -> None:
        self._jobs = database[JOBS_COLLECTION]

    async def list_stale_candidates(
        self,
        *,
        not_seen_days: int,
        source: str | None = None,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        if not_seen_days <= 0:
            return []
        cutoff = datetime.now(UTC) - timedelta(days=not_seen_days)
        query: dict[str, Any] = {
            "status": JobStatus.ACTIVE.value,
            "last_seen_at": {"$lt": cutoff},
        }
        if source:
            query["source"] = source
        cursor = self._jobs.find(query).sort("last_seen_at", 1).limit(limit)
        return await cursor.to_list(length=limit)

    async def apply_stale_status(
        self,
        *,
        not_seen_days: int,
        source: str | None = None,
        dry_run: bool = True,
        limit: int = 100,
    ) -> dict[str, int]:
        """
        Manual operator action only. Does not run from collection or Beat by default.
        """
        candidates = await self.list_stale_candidates(
            not_seen_days=not_seen_days,
            source=source,
            limit=limit,
        )
        if dry_run or not candidates:
            return {"candidates": len(candidates), "updated": 0}
        ids = [doc["_id"] for doc in candidates]
        result = await self._jobs.update_many(
            {"_id": {"$in": ids}, "status": JobStatus.ACTIVE.value},
            {"$set": {"status": JobStatus.STALE.value}},
        )
        return {"candidates": len(candidates), "updated": result.modified_count}

    async def list_public_expiry_candidates(
        self,
        *,
        max_age_days: int,
        source: str | None = None,
        limit: int = 200,
        now: datetime | None = None,
    ) -> list[dict[str, Any]]:
        if max_age_days <= 0:
            return []
        clock = now or datetime.now(UTC)
        cutoff = clock - timedelta(days=max_age_days)
        query: dict[str, Any] = {"status": JobStatus.ACTIVE.value}
        if source:
            query["source"] = source
        cursor = self._jobs.find(query).sort([("posted_at", 1), ("first_seen_at", 1)]).limit(limit * 3)
        docs = await cursor.to_list(length=limit * 3)
        out: list[dict[str, Any]] = []
        for doc in docs:
            anchor = effective_public_listing_date(doc)
            if anchor is None or anchor < cutoff:
                out.append(doc)
            if len(out) >= limit:
                break
        return out

    async def apply_public_listing_expiry(
        self,
        *,
        max_age_days: int,
        source: str | None = None,
        dry_run: bool = True,
        limit: int = 200,
        batch_id: str | None = None,
    ) -> dict[str, Any]:
        """
        Mark jobs EXPIRED when public display age exceeds max_age_days.
        Uses posted_at, else first_seen_at. Does not use last_seen_at.
        Idempotent: already-expired rows are skipped.
        """
        candidates = await self.list_public_expiry_candidates(
            max_age_days=max_age_days,
            source=source,
            limit=limit,
        )
        if dry_run or not candidates:
            return {
                "dry_run": dry_run,
                "candidates": len(candidates),
                "updated": 0,
                "batch_id": batch_id,
                "reason_code": "public_listing_max_age",
            }
        now = datetime.now(UTC)
        updated = 0
        for doc in candidates:
            result = await self._jobs.update_one(
                {"_id": doc["_id"], "status": JobStatus.ACTIVE.value},
                {
                    "$set": {
                        "status": JobStatus.EXPIRED.value,
                        "expired_at": now,
                        "expiry_reason": "public_listing_max_age",
                        "expiry_batch_id": batch_id,
                    }
                },
            )
            updated += int(result.modified_count)
        return {
            "dry_run": False,
            "candidates": len(candidates),
            "updated": updated,
            "batch_id": batch_id,
            "reason_code": "public_listing_max_age",
        }
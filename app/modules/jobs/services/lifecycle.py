"""Job lifecycle helpers (no automatic stale/closed from partial collection)."""

from datetime import UTC, datetime, timedelta
from typing import Any

from pymongo.asynchronous.database import AsyncDatabase

from app.database.indexes import JOBS_COLLECTION
from app.modules.jobs.models.job import JobStatus


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
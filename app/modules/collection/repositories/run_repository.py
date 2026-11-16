from datetime import UTC, datetime
from typing import Any

from pymongo.asynchronous.collection import AsyncCollection
from pymongo.asynchronous.database import AsyncDatabase

from app.database.collection_indexes import COLLECTION_RUNS
from app.modules.collection.models.enums import CollectionRunStatus
from app.modules.collection.models.run import CollectionRun
from app.modules.collection.repositories.checkpoint_repository import (
    normalize_search_location_key,
)
from app.modules.jobs.models.job import JobSource


class RunRepository:
    def __init__(self, database: AsyncDatabase[Any]) -> None:
        self._collection: AsyncCollection[Any] = database[COLLECTION_RUNS]

    async def create_run(self, run: CollectionRun) -> dict[str, Any]:
        payload = run.model_dump(mode="python")
        for key in ("source", "status"):
            payload[key] = payload[key].value if hasattr(payload[key], "value") else payload[key]
        await self._collection.insert_one(payload)
        doc = await self._collection.find_one({"run_id": run.run_id})
        if doc is None:
            raise RuntimeError("Run insert failed")
        return doc

    async def update_status(
        self,
        run_id: str,
        *,
        status: CollectionRunStatus,
        stats: dict[str, int] | None = None,
        error_summary: str | None = None,
    ) -> None:
        update: dict[str, Any] = {"status": status.value}
        if stats:
            update.update(stats)
        if error_summary is not None:
            update["error_summary"] = error_summary
        terminal = {
            CollectionRunStatus.COMPLETED,
            CollectionRunStatus.FAILED,
            CollectionRunStatus.CANCELLED,
        }
        if status in terminal:
            update["finished_at"] = datetime.now(UTC)
        await self._collection.update_one({"run_id": run_id}, {"$set": update})

    async def get_active_for_target(
        self,
        *,
        source: JobSource,
        country_code: str,
        keyword: str,
        search_location: str | None = None,
    ) -> dict[str, Any] | None:
        loc_key = normalize_search_location_key(search_location)
        query: dict[str, Any] = {
            "source": source.value,
            "country_code": country_code.upper(),
            "keyword": keyword.strip().lower(),
            "status": CollectionRunStatus.RUNNING.value,
        }
        if loc_key:
            query["search_location"] = loc_key
        else:
            query["$or"] = [
                {"search_location": ""},
                {"search_location": {"$exists": False}},
            ]
        return await self._collection.find_one(query)

    async def cancel_if_running(
        self,
        run_id: str,
        *,
        error_summary: str | None = None,
    ) -> bool:
        update: dict[str, Any] = {
            "status": CollectionRunStatus.CANCELLED.value,
            "finished_at": datetime.now(UTC),
        }
        if error_summary is not None:
            update["error_summary"] = error_summary
        result = await self._collection.update_one(
            {"run_id": run_id, "status": CollectionRunStatus.RUNNING.value},
            {"$set": update},
        )
        return result.matched_count == 1

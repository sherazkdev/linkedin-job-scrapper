from typing import Any

from pymongo.asynchronous.collection import AsyncCollection
from pymongo.asynchronous.database import AsyncDatabase

from app.database.collection_indexes import COVERAGE_TARGETS


class CoverageTargetRepository:
    def __init__(self, database: AsyncDatabase[Any]) -> None:
        self._collection: AsyncCollection[Any] = database[COVERAGE_TARGETS]

    async def import_targets(
        self,
        rows: list[dict[str, str]],
        *,
        schema_version: int,
        apply: bool,
    ) -> dict[str, int]:
        scanned = len(rows)
        would_insert = 0
        inserted = 0
        unchanged = 0
        for row in rows:
            existing = await self._collection.find_one({"target_id": row["target_id"]})
            if existing is None:
                would_insert += 1
                if apply:
                    await self._collection.insert_one(
                        {
                            **row,
                            "enabled": False,
                            "schema_version": schema_version,
                            "collection_status": "awaiting_approved_source",
                            "supported_sources": [],
                        }
                    )
                    inserted += 1
            else:
                unchanged += 1
                if apply:
                    await self._collection.update_one(
                        {"target_id": row["target_id"]},
                        {
                            "$set": {
                                "country_name": row["country_name"],
                                "keyword_display": row["keyword_display"],
                                "schema_version": schema_version,
                            }
                        },
                    )
        if not apply:
            return {
                "scanned": scanned,
                "would_insert": would_insert,
                "would_update_metadata": unchanged,
                "inserted": 0,
            }
        return {
            "scanned": scanned,
            "inserted": inserted,
            "updated_metadata": unchanged,
            "would_insert": 0,
        }

    async def count_all(self) -> int:
        return await self._collection.count_documents({})

    async def count_enabled(self) -> int:
        return await self._collection.count_documents({"enabled": True})

    async def count_source_supported(self) -> int:
        return await self._collection.count_documents(
            {"supported_sources.0": {"$exists": True}}
        )

    async def count_approved_active(self) -> int:
        return await self._collection.count_documents(
            {
                "enabled": True,
                "supported_sources.0": {"$exists": True},
                "collection_status": "approved",
            }
        )

    async def compare_with_collection_targets(self, database: AsyncDatabase[Any]) -> dict[str, Any]:
        from app.database.collection_indexes import COLLECTION_TARGETS

        sched = database[COLLECTION_TARGETS]
        sched_count = await sched.count_documents({})
        sched_countries = await sched.distinct("country_code")
        sched_keywords = await sched.distinct("keyword")
        sched_enabled = await sched.count_documents({"enabled": True})
        return {
            "collection_targets_total": sched_count,
            "collection_targets_enabled": sched_enabled,
            "collection_target_countries": len(sched_countries),
            "collection_target_keywords": len(sched_keywords),
        }
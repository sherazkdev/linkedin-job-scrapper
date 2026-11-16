from typing import Any

from pymongo.asynchronous.collection import AsyncCollection
from pymongo.asynchronous.database import AsyncDatabase

from app.database.collection_indexes import COLLECTION_CHECKPOINTS
from app.modules.jobs.models.job import JobSource


def normalize_search_location_key(search_location: str | None) -> str:
    """Strip and lower-case; empty string for country-wide / unset searches."""
    if search_location is None:
        return ""
    stripped = search_location.strip()
    if not stripped:
        return ""
    return stripped.lower()


normalize_checkpoint_search_location = normalize_search_location_key


class CheckpointRepository:
    def __init__(self, database: AsyncDatabase[Any]) -> None:
        self._collection: AsyncCollection[Any] = database[COLLECTION_CHECKPOINTS]

    def _filter_key(
        self,
        *,
        source: JobSource,
        country_code: str,
        keyword: str,
        search_location: str | None = None,
    ) -> dict[str, str]:
        return {
            "source": source.value,
            "country_code": country_code.upper(),
            "keyword": keyword.strip().lower(),
            "search_location": normalize_checkpoint_search_location(search_location),
        }

    async def load(
        self,
        *,
        source: JobSource,
        country_code: str,
        keyword: str,
        search_location: str | None = None,
    ) -> dict[str, Any] | None:
        doc = await self._collection.find_one(
            self._filter_key(
                source=source,
                country_code=country_code,
                keyword=keyword,
                search_location=search_location,
            )
        )
        if not doc:
            return None
        return doc.get("checkpoint")

    async def save(
        self,
        *,
        source: JobSource,
        country_code: str,
        keyword: str,
        checkpoint: dict[str, Any],
        search_location: str | None = None,
    ) -> None:
        key = self._filter_key(
            source=source,
            country_code=country_code,
            keyword=keyword,
            search_location=search_location,
        )
        await self._collection.update_one(
            key,
            {
                "$set": {
                    **key,
                    "checkpoint": checkpoint,
                }
            },
            upsert=True,
        )
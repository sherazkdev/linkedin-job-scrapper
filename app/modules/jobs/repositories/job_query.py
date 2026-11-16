from math import ceil
from typing import Any

from bson import ObjectId
from pymongo.asynchronous.collection import AsyncCollection

from app.modules.jobs.models.job import JobStatus
from app.modules.jobs.schemas.filters import JobListFilters, build_mongo_query, sort_spec

LIST_PROJECTION = {
    "_id": 1,
    "source": 1,
    "sourceJobId": 1,
    "title": 1,
    "company": 1,
    "country_code": 1,
    "search_country_code": 1,
    "location_text": 1,
    "city": 1,
    "region": 1,
    "is_remote": 1,
    "employment_type": 1,
    "workplace_type": 1,
    "job_url": 1,
    "posted_at": 1,
    "last_seen_at": 1,
    "status": 1,
    "description_provided": 1,
    "data_provenance": 1,
}


class JobQueryRepository:
    def __init__(self, collection: AsyncCollection[Any]) -> None:
        self._collection = collection

    async def search_jobs(
        self,
        *,
        filters: JobListFilters,
        page: int,
        page_size: int,
    ) -> tuple[list[dict[str, Any]], int]:
        query = build_mongo_query(filters)
        total = await self._collection.count_documents(query)
        skip = (page - 1) * page_size
        cursor = (
            self._collection.find(query, projection=LIST_PROJECTION)
            .sort(sort_spec(filters.sort))
            .skip(skip)
            .limit(page_size)
        )
        items = await cursor.to_list(length=page_size)
        return items, total

    async def get_by_id(self, job_id: str) -> dict[str, Any] | None:
        if not ObjectId.is_valid(job_id):
            return None
        return await self._collection.find_one({"_id": ObjectId(job_id)})

    async def aggregate_stats(self) -> dict[str, Any]:
        active = {"status": JobStatus.ACTIVE.value}
        total_active = await self._collection.count_documents(active)
        remote_active = await self._collection.count_documents(
            {
                **active,
                "$or": [{"is_remote": True}, {"workplace_type": "remote"}],
            }
        )
        unknown_country = await self._collection.count_documents(
            {
                **active,
                "$or": [{"country_code": None}, {"country_code": {"$exists": False}}],
            }
        )

        by_job_country = await self._group_count(active, "$country_code", exclude_null=True)
        by_search_market = await self._group_count(
            active,
            "$search_country_code",
            exclude_null=True,
        )
        by_source = await self._group_count(active, "$source")
        by_employment = await self._group_count(active, "$employment_type")

        return {
            "total_active": total_active,
            "by_job_country": by_job_country,
            "by_search_market": by_search_market,
            "by_source": by_source,
            "by_employment_type": by_employment,
            "remote_active": remote_active,
            "unknown_job_country_active": unknown_country,
        }

    async def list_countries(self) -> dict[str, list[dict[str, int | str]]]:
        active = {"status": JobStatus.ACTIVE.value}
        job_countries = await self._group_count(active, "$country_code", exclude_null=True)
        search_markets = await self._group_count(active, "$search_country_code", exclude_null=True)
        return {
            "job_countries": job_countries,
            "search_markets": search_markets,
        }

    async def _group_count(
        self,
        match: dict[str, Any],
        field: str,
        *,
        exclude_null: bool = False,
    ) -> list[dict[str, Any]]:
        pipeline: list[dict[str, Any]] = [{"$match": match}]
        if exclude_null:
            fld = field.lstrip("$")
            pipeline[0]["$match"] = {**pipeline[0]["$match"], fld: {"$nin": [None, ""]}}
        pipeline.extend(
            [
                {"$group": {"_id": field, "count": {"$sum": 1}}},
                {"$sort": {"count": -1}},
            ]
        )
        rows: list[dict[str, Any]] = []
        cursor = await self._collection.aggregate(pipeline)
        async for row in cursor:
            key = row["_id"]
            if key is None:
                continue
            rows.append({"code": str(key).upper(), "active_jobs": int(row["count"])})
        return rows


def pagination_meta(total: int, page: int, page_size: int) -> dict[str, int | bool]:
    total_pages = max(1, ceil(total / page_size)) if page_size else 1
    return {
        "total": total,
        "page": page,
        "page_size": page_size,
        "total_pages": total_pages,
        "has_next": page < total_pages,
        "has_previous": page > 1,
        "has_more": page < total_pages,
    }
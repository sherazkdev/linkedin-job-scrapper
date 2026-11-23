from datetime import UTC, datetime
from typing import Any

from bson import ObjectId
from pymongo import ReturnDocument
from pymongo.asynchronous.collection import AsyncCollection
from pymongo.asynchronous.database import AsyncDatabase
from pymongo.errors import DuplicateKeyError

from app.database.indexes import JOBS_COLLECTION
from app.modules.collection.models.enums import JobUpsertOutcome
from app.modules.jobs.models.job import JobDocument, JobStatus
from app.modules.jobs.repositories.job_query import LIST_PROJECTION
from app.modules.jobs.schemas.filters import JobListFilters, build_mongo_query, sort_spec

_COMPARE_FIELDS = (
    "title",
    "company",
    "search_country_code",
    "country_code",
    "location_text",
    "city",
    "region",
    "is_remote",
    "description",
    "employment_type",
    "workplace_type",
    "job_url",
    "posted_at",
    "source_posting_label",
    "source_updated_at",
    "description_provided",
)

_REACTIVATE_STATUSES = {
    JobStatus.STALE.value,
    JobStatus.EXPIRED.value,
    JobStatus.UNKNOWN.value,
}


class JobRepository:
    def __init__(self, database: AsyncDatabase[Any]) -> None:
        self._collection: AsyncCollection[Any] = database[JOBS_COLLECTION]

    async def upsert_job(self, job: JobDocument) -> tuple[dict[str, Any], bool]:
        """
        Insert or update a job by (source, sourceJobId).
        Returns (document, created) where created is True if a new row was inserted.
        """
        now = datetime.now(UTC)
        payload = job.to_mongo()
        payload["last_seen_at"] = now

        try:
            filter_doc = {
                "source": payload["source"],
                "sourceJobId": payload["sourceJobId"],
            }
            result = await self._collection.update_one(
                filter_doc,
                {
                    "$set": {
                        k: v
                        for k, v in payload.items()
                        if k not in {"first_seen_at", "source", "sourceJobId"}
                    },
                    "$setOnInsert": {
                        "source": payload["source"],
                        "sourceJobId": payload["sourceJobId"],
                        "first_seen_at": job.first_seen_at,
                    },
                },
                upsert=True,
            )
            doc = await self._collection.find_one(filter_doc)
            if doc is None:
                raise RuntimeError("Upsert succeeded but document not found")
            created = result.upserted_id is not None
            return doc, created
        except DuplicateKeyError:
            doc = await self._collection.find_one_and_update(
                {"source": payload["source"], "sourceJobId": payload["sourceJobId"]},
                {"$set": {**payload, "last_seen_at": now}},
                return_document=ReturnDocument.AFTER,
            )
            if doc is None:
                raise
            return doc, False

    async def get_by_id(self, job_id: str) -> dict[str, Any] | None:
        if not ObjectId.is_valid(job_id):
            return None
        return await self._collection.find_one({"_id": ObjectId(job_id)})

    async def search_jobs(
        self,
        *,
        filters: JobListFilters,
        page: int,
        page_size: int,
        public_listing_max_age_days: int | None = None,
    ) -> tuple[list[dict[str, Any]], int]:
        query = build_mongo_query(
            filters,
            public_listing_max_age_days=public_listing_max_age_days,
        )
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

    async def aggregate_public_stats(self) -> dict[str, Any]:
        from app.modules.jobs.repositories.job_query import JobQueryRepository

        return await JobQueryRepository(self._collection).aggregate_stats()

    async def list_country_aggregates(self) -> dict[str, list[dict[str, Any]]]:
        from app.modules.jobs.repositories.job_query import JobQueryRepository

        return await JobQueryRepository(self._collection).list_countries()

    def _content_changed(self, existing: dict[str, Any], payload: dict[str, Any]) -> bool:
        for field in _COMPARE_FIELDS:
            left = existing.get(field)
            right = payload.get(field)
            if field == "posted_at":
                left = self._normalize_posted_at(left)
                right = self._normalize_posted_at(right)
                posting_label = existing.get("source_posting_label")
                if (
                    posting_label
                    and posting_label == payload.get("source_posting_label")
                    and self._values_equivalent(left, right) is False
                ):
                    # Relative labels (e.g. "2 days ago") derive posted_at from wall clock;
                    # identical label means no substantive listing change.
                    continue
            if self._values_equivalent(left, right):
                continue
            return True
        return False

    @staticmethod
    def _values_equivalent(left: Any, right: Any) -> bool:
        if left is None or left == "":
            left = None
        if right is None or right == "":
            right = None
        return left == right

    @staticmethod
    def _normalize_posted_at(value: Any) -> datetime | None:
        if value is None:
            return None
        if not isinstance(value, datetime):
            return value
        if value.tzinfo is None:
            return value.replace(tzinfo=UTC)
        return value.astimezone(UTC)

    async def upsert_job_tracked(self, job: JobDocument) -> tuple[dict[str, Any], JobUpsertOutcome]:
        now = datetime.now(UTC)
        payload = job.to_mongo()
        filter_doc = {"source": payload["source"], "sourceJobId": payload["sourceJobId"]}
        existing = await self._collection.find_one(filter_doc)

        if existing is None:
            doc, created = await self.upsert_job(job)
            if not created:
                return doc, JobUpsertOutcome.UPDATED
            return doc, JobUpsertOutcome.CREATED

        if not self._content_changed(existing, payload):
            touch: dict[str, Any] = {"last_seen_at": now}
            if existing.get("status") in _REACTIVATE_STATUSES:
                touch["status"] = JobStatus.ACTIVE.value
            await self._collection.update_one(filter_doc, {"$set": touch})
            refreshed = await self._collection.find_one(filter_doc)
            if refreshed is None:
                raise RuntimeError("Job disappeared after touch update")
            return refreshed, JobUpsertOutcome.UNCHANGED

        set_fields = {
            k: v
            for k, v in payload.items()
            if k not in {"first_seen_at", "source", "sourceJobId"}
        }
        set_fields["last_seen_at"] = now
        if existing.get("status") in _REACTIVATE_STATUSES:
            set_fields["status"] = JobStatus.ACTIVE.value
        try:
            await self._collection.update_one(filter_doc, {"$set": set_fields})
        except DuplicateKeyError:
            doc, _ = await self.upsert_job(job)
            return doc, JobUpsertOutcome.UPDATED

        updated = await self._collection.find_one(filter_doc)
        if updated is None:
            raise RuntimeError("Job not found after content update")
        return updated, JobUpsertOutcome.UPDATED

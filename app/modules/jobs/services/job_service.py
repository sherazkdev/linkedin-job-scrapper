from math import ceil
from typing import Any

from app.core.exceptions import AppError, NotFoundError
from app.modules.jobs.models.job import JobDataProvenance, JobDocument
from app.modules.jobs.provenance import infer_provenance_from_job_document
from app.modules.jobs.repositories.job_repository import JobRepository
from app.modules.jobs.schemas.filters import JobListFilters
from app.modules.jobs.schemas.job import (
    CountryAggregate,
    JobListResponse,
    JobResponse,
    JobStatsResponse,
    JobSummaryResponse,
    PaginationParams,
    SearchCountryAggregate,
)


def _search_cc(doc: dict[str, Any]) -> str | None:
    raw = doc.get("search_country_code") or doc.get("country_code")
    return str(raw).upper() if raw else None


def _doc_to_summary(doc: dict[str, Any]) -> JobSummaryResponse:
    source_job_id = doc.get("source_job_id") or doc["sourceJobId"]
    return JobSummaryResponse(
        id=str(doc["_id"]),
        source=doc["source"],
        source_job_id=source_job_id,
        title=doc["title"],
        company=doc["company"],
        country_code=doc.get("country_code"),
        search_country_code=_search_cc(doc),
        location_text=doc.get("location_text"),
        city=doc.get("city"),
        region=doc.get("region"),
        is_remote=doc.get("is_remote"),
        employment_type=doc["employment_type"],
        workplace_type=doc["workplace_type"],
        job_url=doc["job_url"],
        posted_at=doc.get("posted_at"),
        last_seen_at=doc["last_seen_at"],
        status=doc["status"],
        description_provided=bool(doc.get("description_provided", True)),
        data_provenance=_provenance_for_doc(doc),
    )


def _provenance_for_doc(doc: dict[str, Any]) -> JobDataProvenance:
    raw = doc.get("data_provenance")
    if isinstance(raw, str):
        try:
            return JobDataProvenance(raw)
        except ValueError:
            pass
    return infer_provenance_from_job_document(doc)


def _doc_to_response(doc: dict[str, Any]) -> JobResponse:
    summary = _doc_to_summary(doc)
    return JobResponse(
        **summary.model_dump(),
        description=doc.get("description") or "",
        source_posting_label=doc.get("source_posting_label"),
        source_updated_at=doc.get("source_updated_at"),
        first_seen_at=doc["first_seen_at"],
    )


class JobService:
    def __init__(self, repository: JobRepository) -> None:
        self._repository = repository

    async def get_job(self, job_id: str) -> JobResponse:
        doc = await self._repository.get_by_id(job_id)
        if doc is None:
            raise NotFoundError("Job not found")
        return _doc_to_response(doc)

    async def list_jobs(
        self,
        pagination: PaginationParams,
        filters: JobListFilters,
    ) -> JobListResponse:
        if filters.country_unknown and filters.country_code:
            raise AppError(
                "country_unknown cannot be combined with country_code",
                code="validation_error",
            )
        items, total = await self._repository.search_jobs(
            filters=filters,
            page=pagination.page,
            page_size=pagination.page_size,
        )
        total_pages = max(1, ceil(total / pagination.page_size)) if pagination.page_size else 1
        has_next = pagination.page < total_pages
        return JobListResponse(
            items=[_doc_to_summary(d) for d in items],
            total=total,
            page=pagination.page,
            page_size=pagination.page_size,
            total_pages=total_pages,
            has_next=has_next,
            has_previous=pagination.page > 1,
            has_more=has_next,
        )

    async def get_stats(self) -> JobStatsResponse:
        raw = await self._repository.aggregate_public_stats()
        return JobStatsResponse(
            total_active=int(raw["total_active"]),
            by_job_country=[
                CountryAggregate(country_code=row["code"], active_jobs=row["active_jobs"])
                for row in raw["by_job_country"]
            ],
            by_search_market=[
                SearchCountryAggregate(
                    search_country_code=row["code"],
                    active_jobs=row["active_jobs"],
                )
                for row in raw["by_search_market"]
            ],
            by_source={str(k): int(v) for k, v in self._rows_to_dict(raw["by_source"]).items()},
            by_employment_type={
                str(k): int(v) for k, v in self._rows_to_dict(raw["by_employment_type"]).items()
            },
            remote_active=int(raw["remote_active"]),
            unknown_job_country_active=int(raw["unknown_job_country_active"]),
        )

    async def list_countries(self) -> dict[str, Any]:
        data = await self._repository.list_country_aggregates()
        return {
            "job_countries": [
                CountryAggregate(country_code=row["code"], active_jobs=row["active_jobs"])
                for row in data["job_countries"]
            ],
            "search_markets": [
                SearchCountryAggregate(
                    search_country_code=row["code"],
                    active_jobs=row["active_jobs"],
                )
                for row in data["search_markets"]
            ],
        }

    @staticmethod
    def _rows_to_dict(rows: list[dict[str, Any]]) -> dict[str, int]:
        return {row["code"]: row["active_jobs"] for row in rows}

    async def upsert_job(self, job: JobDocument) -> tuple[JobResponse, bool]:
        doc, created = await self._repository.upsert_job(job)
        return _doc_to_response(doc), created
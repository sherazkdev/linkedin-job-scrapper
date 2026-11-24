from typing import Annotated

from fastapi import APIRouter, Depends, Query

from app.api.deps import get_job_service
from app.core.config import get_settings
from app.core.exceptions import AppError
from app.modules.jobs.models.job import (
    EmploymentType,
    JobDataProvenance,
    JobSource,
    JobStatus,
    WorkplaceType,
)
from app.modules.jobs.schemas.filters import JobListFilters, JobSort
from app.modules.jobs.schemas.job import PaginationParams
from app.modules.jobs.services.job_service import JobService

router = APIRouter(prefix="/api/v1/jobs", tags=["jobs"])


def _pagination(page: int, page_size: int | None) -> PaginationParams:
    settings = get_settings()
    if page > settings.jobs_max_page:
        raise AppError(
            f"page cannot exceed {settings.jobs_max_page}",
            code="validation_error",
        )
    size = page_size or settings.jobs_default_page_size
    if size > settings.jobs_max_page_size:
        size = settings.jobs_max_page_size
    return PaginationParams(page=page, page_size=size)


@router.get("/stats", response_model=dict)
async def job_stats(service: Annotated[JobService, Depends(get_job_service)]) -> dict:
    data = await service.get_stats()
    return {"success": True, "data": data.model_dump(mode="json")}


@router.get("", response_model=dict)
async def list_jobs(
    service: Annotated[JobService, Depends(get_job_service)],
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int | None, Query(ge=1, le=100)] = None,
    country_code: Annotated[str | None, Query(min_length=2, max_length=2)] = None,
    search_country_code: Annotated[str | None, Query(min_length=2, max_length=2)] = None,
    country_unknown: Annotated[bool | None, Query()] = None,
    q: Annotated[str | None, Query(max_length=200)] = None,
    city: Annotated[str | None, Query(max_length=120)] = None,
    source: Annotated[JobSource | None, Query()] = None,
    employment_type: Annotated[EmploymentType | None, Query()] = None,
    workplace_type: Annotated[WorkplaceType | None, Query()] = None,
    is_remote: Annotated[bool | None, Query()] = None,
    status: Annotated[JobStatus | None, Query()] = None,
    posted_within: Annotated[int | None, Query(ge=1, le=365, alias="posted_within")] = None,
    data_provenance: Annotated[JobDataProvenance | None, Query()] = None,
    live_verified_only: Annotated[bool, Query()] = False,
    sort: Annotated[JobSort, Query()] = JobSort.POSTED_AT_DESC,
) -> dict:
    try:
        filters = JobListFilters(
            country_code=country_code,
            search_country_code=search_country_code,
            country_unknown=country_unknown,
            q=q,
            city=city,
            source=source,
            employment_type=employment_type,
            workplace_type=workplace_type,
            is_remote=is_remote,
            status=status or JobStatus.ACTIVE,
            posted_within_days=posted_within,
            data_provenance=data_provenance,
            live_verified_only=live_verified_only,
            sort=sort,
        )
    except ValueError as exc:
        raise AppError(str(exc), code="validation_error") from exc

    data = await service.list_jobs(_pagination(page, page_size), filters)
    return {"success": True, "data": data.model_dump(mode="json")}


@router.get("/{job_id}", response_model=dict)
async def get_job(
    job_id: str,
    service: Annotated[JobService, Depends(get_job_service)],
) -> dict:
    data = await service.get_job(job_id)
    return {"success": True, "data": data.model_dump(mode="json")}
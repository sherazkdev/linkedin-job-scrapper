from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.modules.jobs.models.job import (
    EmploymentType,
    JobDataProvenance,
    JobSource,
    JobStatus,
    WorkplaceType,
)


class JobSummaryResponse(BaseModel):
    """Listing payload (no full description)."""

    model_config = ConfigDict(from_attributes=True)

    id: str
    source: JobSource
    source_job_id: str
    title: str
    company: str
    country_code: str | None = None
    search_country_code: str | None = None
    location_text: str | None = None
    city: str | None = None
    region: str | None = None
    is_remote: bool | None = None
    employment_type: EmploymentType
    workplace_type: WorkplaceType
    job_url: str
    posted_at: datetime | None = None
    last_seen_at: datetime
    status: JobStatus
    description_provided: bool = True
    data_provenance: JobDataProvenance = JobDataProvenance.UNKNOWN


class JobResponse(JobSummaryResponse):
    description: str = ""
    source_posting_label: str | None = None
    source_updated_at: datetime | None = None
    first_seen_at: datetime


class JobListResponse(BaseModel):
    items: list[JobSummaryResponse]
    total: int
    page: int
    page_size: int
    total_pages: int
    has_next: bool
    has_previous: bool
    has_more: bool  # legacy alias for has_next


class PaginationParams(BaseModel):
    page: int = Field(default=1, ge=1)
    page_size: int = Field(default=20, ge=1, le=100)


class CountryAggregate(BaseModel):
    country_code: str
    active_jobs: int


class SearchCountryAggregate(BaseModel):
    search_country_code: str
    active_jobs: int


class JobStatsResponse(BaseModel):
    total_active: int
    by_job_country: list[CountryAggregate]
    by_search_market: list[SearchCountryAggregate]
    by_source: dict[str, int]
    by_employment_type: dict[str, int]
    remote_active: int
    unknown_job_country_active: int
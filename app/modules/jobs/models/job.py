from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field


class JobStatus(StrEnum):
    ACTIVE = "active"
    STALE = "stale"
    CLOSED = "closed"
    UNKNOWN = "unknown"
    EXPIRED = "expired"  # legacy alias; prefer STALE for new lifecycle logic


class EmploymentType(StrEnum):
    FULL_TIME = "full_time"
    PART_TIME = "part_time"
    CONTRACT = "contract"
    TEMPORARY = "temporary"
    INTERNSHIP = "internship"
    OTHER = "other"


class WorkplaceType(StrEnum):
    ON_SITE = "on_site"
    REMOTE = "remote"
    HYBRID = "hybrid"
    UNKNOWN = "unknown"


class JobSource(StrEnum):
    """Known sources; extend when adapters are added."""

    DEMO = "demo"
    FIXTURE = "fixture"
    LINKEDIN = "linkedin"
    GREENHOUSE = "greenhouse"
    LEVER = "lever"
    ASHBY = "ashby"
    ADZUNA = "adzuna"


class JobDataProvenance(StrEnum):
    """How the job entered the store — independent of JobSource label."""

    SYNTHETIC_FIXTURE = "synthetic_fixture"
    DEMO_SEED = "demo_seed"
    OFFLINE_PROVIDER_FIXTURE = "offline_provider_fixture"
    LIVE_API_VERIFIED = "live_api_verified"
    UNKNOWN = "unknown"


class JobDocument(BaseModel):
    """Normalized job document stored in MongoDB."""

    model_config = ConfigDict(populate_by_name=True)

    source: JobSource
    source_job_id: str
    title: str
    company: str
    search_country_code: str = Field(min_length=2, max_length=2, pattern=r"^[A-Z]{2}$")
    country_code: str | None = Field(
        default=None,
        min_length=2,
        max_length=2,
        pattern=r"^[A-Z]{2}$",
    )
    location_text: str | None = None
    city: str | None = None
    region: str | None = None
    is_remote: bool | None = None
    description: str = ""
    description_provided: bool = True
    source_posting_label: str | None = None
    source_updated_at: datetime | None = None
    employment_type: EmploymentType = EmploymentType.OTHER
    workplace_type: WorkplaceType = WorkplaceType.UNKNOWN
    job_url: str
    posted_at: datetime | None = None
    first_seen_at: datetime
    last_seen_at: datetime
    status: JobStatus = JobStatus.ACTIVE
    data_provenance: JobDataProvenance = JobDataProvenance.UNKNOWN

    def to_mongo(self) -> dict:
        data = self.model_dump(mode="python")
        for key in ("source", "employment_type", "workplace_type", "status", "data_provenance"):
            data[key] = data[key].value if hasattr(data[key], "value") else data[key]
        data["sourceJobId"] = data.pop("source_job_id")
        return data

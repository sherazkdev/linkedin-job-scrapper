import re
from datetime import UTC, datetime, timedelta
from enum import StrEnum

from pydantic import BaseModel, Field, field_validator

from app.modules.jobs.models.job import (
    EmploymentType,
    JobDataProvenance,
    JobSource,
    JobStatus,
    WorkplaceType,
)


class JobSort(StrEnum):
    POSTED_AT_DESC = "posted_at_desc"
    POSTED_AT_ASC = "posted_at_asc"
    LAST_SEEN_DESC = "last_seen_desc"
    TITLE_ASC = "title_asc"


class JobListFilters(BaseModel):
    country_code: str | None = Field(default=None, min_length=2, max_length=2)
    search_country_code: str | None = Field(default=None, min_length=2, max_length=2)
    country_unknown: bool | None = None
    q: str | None = Field(default=None, max_length=200)
    source: JobSource | None = None
    employment_type: EmploymentType | None = None
    workplace_type: WorkplaceType | None = None
    is_remote: bool | None = None
    status: JobStatus | None = Field(default=JobStatus.ACTIVE)
    posted_within_days: int | None = Field(default=None, ge=1, le=365)
    data_provenance: JobDataProvenance | None = None
    live_verified_only: bool = False
    sort: JobSort = JobSort.POSTED_AT_DESC

    @field_validator("country_code", "search_country_code")
    @classmethod
    def validate_iso_country(cls, value: str | None) -> str | None:
        if value is None:
            return None
        code = value.strip().upper()
        if len(code) != 2 or not code.isalpha():
            raise ValueError("must be a 2-letter ISO country code")
        return code

    @field_validator("q")
    @classmethod
    def normalize_query(cls, value: str | None) -> str | None:
        if value is None:
            return None
        stripped = value.strip()
        return stripped if stripped else None


def escape_regex(value: str) -> str:
    return re.escape(value)


def build_mongo_query(
    filters: JobListFilters,
    *,
    public_listing_max_age_days: int | None = None,
) -> dict:
    """Build a safe MongoDB filter (no user-controlled operators)."""
    clauses: list[dict] = []

    status = filters.status or JobStatus.ACTIVE
    clauses.append({"status": status.value})

    if filters.country_code is not None:
        clauses.append({"country_code": filters.country_code})

    if filters.search_country_code is not None:
        clauses.append({"search_country_code": filters.search_country_code})

    if filters.country_unknown is True:
        clauses.append({"$or": [{"country_code": None}, {"country_code": {"$exists": False}}]})
    elif filters.country_unknown is False:
        clauses.append({"country_code": {"$nin": [None, ""]}})

    if filters.source is not None:
        clauses.append({"source": filters.source.value})

    if filters.employment_type is not None:
        clauses.append({"employment_type": filters.employment_type.value})

    if filters.workplace_type is not None:
        clauses.append({"workplace_type": filters.workplace_type.value})

    if filters.is_remote is True:
        clauses.append(
            {"$or": [{"is_remote": True}, {"workplace_type": WorkplaceType.REMOTE.value}]}
        )
    elif filters.is_remote is False:
        clauses.append({"is_remote": False})

    if filters.posted_within_days is not None:
        cutoff = datetime.now(UTC) - timedelta(days=filters.posted_within_days)
        clauses.append({"posted_at": {"$gte": cutoff}})

    if filters.q:
        pattern = escape_regex(filters.q)
        clauses.append(
            {
                "$or": [
                    {"title": {"$regex": pattern, "$options": "i"}},
                    {"company": {"$regex": pattern, "$options": "i"}},
                ]
            }
        )

    if filters.live_verified_only:
        clauses.append({"data_provenance": JobDataProvenance.LIVE_API_VERIFIED.value})
    elif filters.data_provenance is not None:
        clauses.append({"data_provenance": filters.data_provenance.value})

    if (
        public_listing_max_age_days is not None
        and public_listing_max_age_days > 0
        and (filters.status or JobStatus.ACTIVE) == JobStatus.ACTIVE
    ):
        from app.modules.jobs.public_visibility import mongo_public_max_age_clause

        clauses.append(mongo_public_max_age_clause(max_age_days=public_listing_max_age_days))

    if len(clauses) == 1:
        return clauses[0]
    return {"$and": clauses}


def sort_spec(sort: JobSort) -> list[tuple[str, int]]:
    """Deterministic ordering with stable pagination tie-breaker."""
    mapping = {
        JobSort.POSTED_AT_DESC: [
            ("posted_at", -1),
            ("first_seen_at", -1),
            ("sourceJobId", -1),
        ],
        JobSort.POSTED_AT_ASC: [
            ("posted_at", 1),
            ("first_seen_at", 1),
            ("sourceJobId", 1),
        ],
        JobSort.LAST_SEEN_DESC: [("last_seen_at", -1), ("sourceJobId", -1)],
        JobSort.TITLE_ASC: [("title", 1), ("sourceJobId", 1)],
    }
    return mapping[sort]
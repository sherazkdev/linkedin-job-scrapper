from datetime import datetime

from pydantic import BaseModel, Field, model_validator


class RawJobRecord(BaseModel):
    """Unvalidated payload from a source adapter."""

    source_job_id: str = Field(min_length=1)
    title: str
    company: str
    search_country_code: str | None = None
    country_code: str | None = None
    location_text: str | None = None
    city: str | None = None
    region: str | None = None
    is_remote: bool | None = None
    description: str
    job_url: str
    employment_type: str | None = None
    workplace_type: str | None = None
    posted_at: datetime | None = None
    source_updated_at: datetime | None = None
    posting_time_text: str | None = None
    posting_time_iso_hint: str | None = None
    description_provided: bool = True

    @model_validator(mode="before")
    @classmethod
    def _legacy_country_as_search(cls, data: object) -> object:
        if not isinstance(data, dict):
            return data
        if data.get("search_country_code") is None and data.get("country_code") is not None:
            data = dict(data)
            data["search_country_code"] = data["country_code"]
        return data
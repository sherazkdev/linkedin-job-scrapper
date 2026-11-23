"""API schemas for job alerts."""

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field, field_validator

from app.modules.jobs.models.job import EmploymentType


class SavedSearchCreate(BaseModel):
    q: str | None = Field(default=None, max_length=200)
    country_code: str | None = Field(default=None, min_length=2, max_length=2)
    city: str | None = Field(
        default=None,
        max_length=120,
        description="Exact match on structured job.city when populated by collection; not full-text location.",
    )
    employment_type: EmploymentType | None = None
    is_remote: bool | None = None
    alerts_enabled: bool = True
    digest_enabled: bool = False
    digest_local_time: str | None = Field(
        default=None,
        pattern=r"^\d{2}:\d{2}$",
        description="HH:MM in digest_timezone",
    )
    digest_timezone: str = Field(default="UTC", max_length=64)
    digest_max_jobs: int = Field(default=10, ge=1, le=50)

    @field_validator("country_code")
    @classmethod
    def upper_country(cls, v: str | None) -> str | None:
        return v.upper() if v else None


class SavedSearchUpdate(BaseModel):
    q: str | None = Field(default=None, max_length=200)
    country_code: str | None = Field(default=None, min_length=2, max_length=2)
    city: str | None = Field(default=None, max_length=120)
    employment_type: EmploymentType | None = None
    is_remote: bool | None = None
    alerts_enabled: bool | None = None
    digest_enabled: bool | None = None
    digest_local_time: str | None = Field(default=None, pattern=r"^\d{2}:\d{2}$")
    digest_timezone: str | None = Field(default=None, max_length=64)
    digest_max_jobs: int | None = Field(default=None, ge=1, le=50)


class SavedSearchOut(BaseModel):
    id: str
    subscriber_id: str
    q: str | None
    country_code: str | None
    city: str | None
    employment_type: str | None
    is_remote: bool | None
    alerts_enabled: bool
    digest_enabled: bool
    digest_local_time: str | None
    digest_timezone: str
    digest_max_jobs: int
    created_at: datetime
    updated_at: datetime


class SubscriberRegisterOut(BaseModel):
    subscriber_id: str
    bearer_token: str = Field(description="Shown once; store securely. Cannot be recovered if lost.")


class NotificationOut(BaseModel):
    id: str
    event_key: str
    job_id: str
    title: str | None = None
    company: str | None = None
    job_url: str | None = None
    read_at: datetime | None
    created_at: datetime
    payload_type: str = "in_app"


class NotificationListOut(BaseModel):
    items: list[NotificationOut]
    total: int
    page: int
    page_size: int
    unread_count: int


class MarkReadBody(BaseModel):
    notification_ids: list[str] | None = None
    mark_all: bool = False
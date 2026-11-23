"""Job alert subscription models (backend foundation — no push credentials required)."""

from datetime import UTC, datetime
from enum import StrEnum

from pydantic import BaseModel, Field

from app.modules.jobs.models.job import EmploymentType


class AlertChannel(StrEnum):
    IN_APP = "in_app"
    PUSH = "push"


class AlertDeliveryStatus(StrEnum):
    PENDING = "pending"
    SENT = "sent"
    SKIPPED = "skipped"
    FAILED = "failed"


class SavedJobSearch(BaseModel):
    """User-owned saved search criteria (device/user id is opaque client token)."""

    subscriber_id: str = Field(min_length=8, max_length=128)
    q: str | None = None
    country_code: str | None = None
    employment_type: EmploymentType | None = None
    is_remote: bool | None = None
    enabled: bool = True
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class JobAlertSubscription(BaseModel):
    subscriber_id: str
    saved_search_id: str
    channel: AlertChannel = AlertChannel.IN_APP
    push_device_token: str | None = None
    enabled: bool = True
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
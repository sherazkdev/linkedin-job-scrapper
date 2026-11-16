from datetime import datetime

from pydantic import BaseModel, Field

from app.modules.jobs.models.job import JobSource


class CollectionTarget(BaseModel):
    country_code: str = Field(min_length=2, max_length=2)
    country_name: str = Field(min_length=1)
    keyword: str = Field(min_length=1)
    source: JobSource
    enabled: bool = True
    priority: int = Field(default=100, ge=0, le=1000)
    last_success_at: datetime | None = None
    next_eligible_at: datetime | None = None
    lock_owner: str | None = None
    locked_until: datetime | None = None

    def target_key(self) -> tuple[str, str, str]:
        return (self.source.value, self.country_code.upper(), self.keyword.strip().lower())

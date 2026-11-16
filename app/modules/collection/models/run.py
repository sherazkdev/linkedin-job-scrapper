from datetime import datetime

from pydantic import BaseModel

from app.modules.collection.models.enums import CollectionRunStatus
from app.modules.jobs.models.job import JobSource


class CollectionRun(BaseModel):
    run_id: str
    source: JobSource
    country_code: str
    keyword: str
    search_location: str = ""
    status: CollectionRunStatus = CollectionRunStatus.PENDING
    started_at: datetime | None = None
    finished_at: datetime | None = None
    collected_count: int = 0
    created_count: int = 0
    updated_count: int = 0
    unchanged_count: int = 0
    rejected_count: int = 0
    failed_count: int = 0
    error_summary: str | None = None
    dry_run: bool = False

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any

from app.modules.collection.models.raw_job import RawJobRecord
from app.modules.jobs.models.job import JobSource


@dataclass(slots=True)
class AdapterFetchResult:
    jobs: list[RawJobRecord] = field(default_factory=list)
    checkpoint: dict[str, Any] = field(default_factory=dict)
    has_more: bool = False
    metrics: dict[str, Any] = field(default_factory=dict)


class JobSourceAdapter(ABC):
    """Fetches raw job records for a country/keyword pair."""

    source: JobSource

    @abstractmethod
    async def fetch_jobs(
        self,
        *,
        country_code: str,
        keyword: str,
        limit: int,
        checkpoint: dict[str, Any] | None,
        search_location: str | None = None,
    ) -> AdapterFetchResult:
        """Return the next page/batch of raw jobs and an updated checkpoint."""

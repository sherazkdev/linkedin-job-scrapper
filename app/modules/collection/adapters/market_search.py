"""Market-search adapter contract (Phase 3E design — no live network in repo default)."""

from abc import abstractmethod
from dataclasses import dataclass
from typing import Any

from app.modules.collection.adapters.base import AdapterFetchResult, JobSourceAdapter
from app.modules.jobs.models.job import JobSource


class MarketSearchNotImplementedError(RuntimeError):
    """Raised when a market-search source is not approved or configured."""


@dataclass(slots=True)
class MarketSearchCheckpoint:
    page: int = 1
    results_seen: int = 0
    last_query_hash: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "page": self.page,
            "results_seen": self.results_seen,
            "last_query_hash": self.last_query_hash,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> "MarketSearchCheckpoint":
        if not data:
            return cls()
        return cls(
            page=int(data.get("page", 1)),
            results_seen=int(data.get("results_seen", 0)),
            last_query_hash=data.get("last_query_hash"),
        )


@dataclass(slots=True)
class MarketSearchQueryBudget:
    """Per-run budget hints for schedulers (metadata only)."""

    max_requests: int = 1
    max_results: int = 50
    cooldown_seconds: int = 3600
    backoff_on_429_seconds: int = 900


class MarketSearchJobSourceAdapter(JobSourceAdapter):
    """
    Extension point for authorized keyword+country search APIs (Adzuna, Jooble, Careerjet, …).

    Implementations must respect allow-live flags and HTTP allowlists in app config.
    """

    source: JobSource

    @abstractmethod
    def provider_id(self) -> str:
        """Stable provider slug, e.g. adzuna, jooble, careerjet."""

    @abstractmethod
    def map_country_code(self, country_code: str) -> str | None:
        """Return provider-specific country/locale key, or None if unsupported."""

    @abstractmethod
    def default_budget(self) -> MarketSearchQueryBudget:
        """Documented request budget for this provider."""

    async def fetch_jobs(
        self,
        *,
        country_code: str,
        keyword: str,
        limit: int,
        checkpoint: dict[str, Any] | None,
        search_location: str | None = None,
    ) -> AdapterFetchResult:
        if self.map_country_code(country_code) is None:
            return AdapterFetchResult(
                jobs=[],
                checkpoint=MarketSearchCheckpoint.from_dict(checkpoint).to_dict(),
                has_more=False,
                metrics={"unsupported_country": country_code, "provider": self.provider_id()},
            )
        raise MarketSearchNotImplementedError(
            f"{self.provider_id()} live fetch disabled until operator approval"
        )


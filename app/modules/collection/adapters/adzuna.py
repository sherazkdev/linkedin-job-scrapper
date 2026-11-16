import json
import logging
from pathlib import Path
from typing import Any
from urllib.parse import quote

from app.core.config import Settings
from app.modules.collection.adapters.base import AdapterFetchResult, JobSourceAdapter
from app.modules.collection.http.client import PublicBoardHttpClient
from app.modules.collection.http.errors import PublicBoardCollectionError, PublicBoardFailureState
from app.modules.collection.market_search.adzuna_parser import adzuna_results_to_raw
from app.modules.coverage.market_providers import ADZUNA_COUNTRY
from app.modules.jobs.models.job import JobSource

logger = logging.getLogger(__name__)

ADZUNA_API_ROOT = "https://api.adzuna.com/v1/api/jobs"


def adzuna_country_slug(country_code: str) -> str | None:
    return ADZUNA_COUNTRY.get(country_code.upper())


class AdzunaJobSourceAdapter(JobSourceAdapter):
    """Adzuna documented job search API (market keyword + country path)."""

    source = JobSource.ADZUNA

    def __init__(
        self,
        *,
        settings: Settings,
        http: PublicBoardHttpClient | None = None,
        offline_fixture: Path | None = None,
        live_enabled: bool = False,
    ) -> None:
        self._settings = settings
        self._http = http or PublicBoardHttpClient(
            timeout_seconds=settings.market_search_http_timeout_seconds,
            min_interval_seconds=settings.market_search_min_interval_seconds,
        )
        self._offline_fixture = offline_fixture
        self._live_enabled = live_enabled

    def _credentials(self) -> tuple[str, str]:
        app_id = (self._settings.adzuna_app_id or "").strip()
        app_key = (self._settings.adzuna_app_key or "").strip()
        if not app_id or not app_key:
            raise PublicBoardCollectionError(
                PublicBoardFailureState.FORBIDDEN,
                "Adzuna credentials missing (ADZUNA_APP_ID / ADZUNA_APP_KEY)",
                retryable=False,
            )
        return app_id, app_key

    def _build_search_url(
        self,
        *,
        slug: str,
        page: int,
        keyword: str,
        app_id: str,
        app_key: str,
    ) -> str:
        what = quote(keyword.strip())
        per_page = max(1, min(self._settings.adzuna_results_per_page, 50))
        return (
            f"{ADZUNA_API_ROOT}/{slug}/search/{page}"
            f"?app_id={quote(app_id)}&app_key={quote(app_key)}"
            f"&what={what}&results_per_page={per_page}&content-type=application/json"
        )

    async def fetch_jobs(
        self,
        *,
        country_code: str,
        keyword: str,
        limit: int,
        checkpoint: dict[str, Any] | None,
        search_location: str | None = None,
    ) -> AdapterFetchResult:
        search_country = country_code.upper()
        slug = adzuna_country_slug(search_country)
        processed_ids: set[str] = set((checkpoint or {}).get("processed_ids", []))
        page = int((checkpoint or {}).get("page", 1))
        pages_fetched = int((checkpoint or {}).get("pages_fetched", 0))

        if slug is None:
            return AdapterFetchResult(
                jobs=[],
                checkpoint={"page": page, "processed_ids": sorted(processed_ids)},
                has_more=False,
                metrics={
                    "unsupported_country": search_country,
                    "source": self.source.value,
                },
            )

        max_pages = max(1, self._settings.adzuna_max_pages_per_run)
        if pages_fetched >= max_pages:
            return AdapterFetchResult(
                jobs=[],
                checkpoint={
                    "page": page,
                    "processed_ids": sorted(processed_ids),
                    "pages_fetched": pages_fetched,
                },
                has_more=False,
                metrics={"page_budget_exhausted": True},
            )

        if self._offline_fixture is not None:
            payload = json.loads(self._offline_fixture.read_text(encoding="utf-8"))
        elif self._live_enabled:
            app_id, app_key = self._credentials()
            url = self._build_search_url(
                slug=slug,
                page=page,
                keyword=keyword,
                app_id=app_id,
                app_key=app_key,
            )
            payload = await self._http.get_json(url)
        else:
            raise PublicBoardCollectionError(
                PublicBoardFailureState.DISABLED,
                "Live Adzuna collection disabled "
                "(set ALLOW_LIVE_MARKET_SEARCH_COLLECTION=true, credentials, and offline fixture).",
            )

        jobs, metrics = adzuna_results_to_raw(
            payload if isinstance(payload, dict) else {},
            adzuna_country_slug=slug,
            search_country_code=search_country,
            keyword=keyword,
            skip_ids=processed_ids,
            limit=limit,
        )
        metrics["source"] = self.source.value
        metrics["page"] = page

        new_processed = processed_ids | {job.source_job_id for job in jobs}
        pages_fetched += 1
        total_on_page = int(metrics.get("listings_seen", 0))
        has_more = total_on_page > 0 and pages_fetched < max_pages and len(jobs) >= limit

        return AdapterFetchResult(
            jobs=jobs,
            checkpoint={
                "processed_ids": sorted(new_processed),
                "page": page + 1 if has_more else page,
                "pages_fetched": pages_fetched,
                "keyword": keyword.lower(),
                "adzuna_slug": slug,
            },
            has_more=has_more,
            metrics=metrics,
        )

    async def aclose(self) -> None:
        await self._http.aclose()
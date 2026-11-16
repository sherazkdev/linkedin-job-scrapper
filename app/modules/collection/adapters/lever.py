import json
import logging
from pathlib import Path
from typing import Any

from app.core.config import Settings
from app.modules.collection.adapters.base import AdapterFetchResult, JobSourceAdapter
from app.modules.collection.boards.parsers import lever_postings_to_raw
from app.modules.collection.boards.validation import validate_board_site
from app.modules.collection.http.client import PublicBoardHttpClient
from app.modules.collection.http.errors import PublicBoardCollectionError, PublicBoardFailureState
from app.modules.jobs.models.job import JobSource

logger = logging.getLogger(__name__)

LEVER_API = "https://api.lever.co/v0/postings"


class LeverJobSourceAdapter(JobSourceAdapter):
    """Public Lever postings API (`mode=json`, unauthenticated site slug)."""

    source = JobSource.LEVER

    def __init__(
        self,
        *,
        settings: Settings,
        board_token: str,
        http: PublicBoardHttpClient | None = None,
        offline_fixture: Path | None = None,
        live_enabled: bool = False,
    ) -> None:
        self._settings = settings
        self._site = validate_board_site(board_token, field_name="board_site").lower()
        self._http = http or PublicBoardHttpClient(
            timeout_seconds=settings.public_board_http_timeout_seconds,
            min_interval_seconds=settings.public_board_min_interval_seconds,
        )
        self._offline_fixture = offline_fixture
        self._live_enabled = live_enabled

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
        processed_ids: set[str] = set((checkpoint or {}).get("processed_ids", []))
        page_offset = int((checkpoint or {}).get("page_offset", 0))

        if self._offline_fixture is not None:
            payload = json.loads(self._offline_fixture.read_text(encoding="utf-8"))
            company_name = str(payload.get("company_name") or self._site.title())
            postings = payload.get("postings") or payload
        elif self._live_enabled:
            company_name, postings = await self._fetch_live()
        else:
            raise PublicBoardCollectionError(
                PublicBoardFailureState.DISABLED,
                "Live Lever collection disabled (ALLOW_LIVE_PUBLIC_BOARD_COLLECTION).",
            )

        if not isinstance(postings, list):
            raise PublicBoardCollectionError(
                PublicBoardFailureState.INVALID_PAYLOAD,
                "Lever postings payload is not a list",
            )

        jobs, metrics = lever_postings_to_raw(
            postings[page_offset:],
            board_site=self._site,
            company_name=company_name,
            search_country_code=search_country,
            keyword=keyword,
            skip_ids=processed_ids,
            limit=limit,
        )
        metrics["site"] = self._site
        metrics["source"] = self.source.value

        new_processed = processed_ids | {job.source_job_id for job in jobs}
        next_offset = page_offset + len(postings)
        has_more = len(postings) > page_offset + limit

        return AdapterFetchResult(
            jobs=jobs,
            checkpoint={
                "processed_ids": sorted(new_processed),
                "page_offset": next_offset,
                "site": self._site,
                "keyword": keyword.lower(),
            },
            has_more=has_more,
            metrics=metrics,
        )

    async def _fetch_live(self) -> tuple[str, list[Any]]:
        postings: list[Any] = []
        skip = 0
        page_size = 100
        while True:
            chunk = await self._http.get_json(
                f"{LEVER_API}/{self._site}?mode=json&skip={skip}&limit={page_size}"
            )
            if not isinstance(chunk, list):
                raise PublicBoardCollectionError(
                    PublicBoardFailureState.INVALID_PAYLOAD,
                    "Unexpected Lever API shape",
                )
            if not chunk:
                break
            postings.extend(chunk)
            if len(chunk) < page_size:
                break
            skip += page_size
        company_name = self._site.replace("-", " ").title()
        return company_name, postings

    async def aclose(self) -> None:
        await self._http.aclose()
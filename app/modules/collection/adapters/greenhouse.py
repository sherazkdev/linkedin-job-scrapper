import json
import logging
from pathlib import Path
from typing import Any

from app.core.config import Settings
from app.modules.collection.adapters.base import AdapterFetchResult, JobSourceAdapter
from app.modules.collection.boards.parsers import greenhouse_jobs_to_raw
from app.modules.collection.boards.validation import validate_board_site
from app.modules.collection.http.client import PublicBoardHttpClient
from app.modules.collection.http.errors import PublicBoardCollectionError, PublicBoardFailureState
from app.modules.jobs.models.job import JobSource

logger = logging.getLogger(__name__)

GREENHOUSE_API = "https://boards-api.greenhouse.io/v1/boards"


class GreenhouseJobSourceAdapter(JobSourceAdapter):
    """Public Greenhouse Job Board API (documented, unauthenticated per-board token)."""

    source = JobSource.GREENHOUSE

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
        self._board_token = validate_board_site(board_token, field_name="board_site").lower()
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
        offset = int((checkpoint or {}).get("list_offset", 0))

        if self._offline_fixture is not None:
            payload = json.loads(self._offline_fixture.read_text(encoding="utf-8"))
            company_name = str(payload.get("company_name") or self._board_token.title())
            list_payload = payload.get("jobs_payload") or payload
        elif self._live_enabled:
            company_name, list_payload = await self._fetch_live_board()
        else:
            raise PublicBoardCollectionError(
                PublicBoardFailureState.DISABLED,
                "Live Greenhouse collection disabled "
                "(set ALLOW_LIVE_PUBLIC_BOARD_COLLECTION=true and provide offline fixture).",
            )

        jobs, metrics = greenhouse_jobs_to_raw(
            list_payload if isinstance(list_payload, dict) else {"jobs": list_payload},
            board_site=self._board_token,
            company_name=company_name,
            search_country_code=search_country,
            keyword=keyword,
            skip_ids=processed_ids,
            limit=limit,
        )
        metrics["board_token"] = self._board_token
        metrics["source"] = self.source.value

        new_processed = processed_ids | {job.source_job_id for job in jobs}
        next_offset = offset + len(jobs)
        has_more = metrics["listings_seen"] > next_offset and len(jobs) >= limit

        return AdapterFetchResult(
            jobs=jobs,
            checkpoint={
                "processed_ids": sorted(new_processed),
                "list_offset": next_offset,
                "board_token": self._board_token,
                "keyword": keyword.lower(),
            },
            has_more=has_more,
            metrics=metrics,
        )

    async def _fetch_live_board(self) -> tuple[str, dict[str, Any]]:
        meta = await self._http.get_json(f"{GREENHOUSE_API}/{self._board_token}")
        company_name = str(meta.get("name") or self._board_token.title())
        jobs_payload = await self._http.get_json(
            f"{GREENHOUSE_API}/{self._board_token}/jobs?content=true"
        )
        return company_name, jobs_payload

    async def aclose(self) -> None:
        await self._http.aclose()
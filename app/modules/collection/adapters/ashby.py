import json
import logging
from pathlib import Path
from typing import Any
from urllib.parse import quote

from app.core.config import Settings
from app.modules.collection.adapters.base import AdapterFetchResult, JobSourceAdapter
from app.modules.collection.boards.parsers import ashby_jobs_to_raw
from app.modules.collection.boards.validation import validate_board_site
from app.modules.collection.http.client import PublicBoardHttpClient
from app.modules.collection.http.errors import PublicBoardCollectionError, PublicBoardFailureState
from app.modules.jobs.models.job import JobSource

logger = logging.getLogger(__name__)

ASHBY_API = "https://api.ashbyhq.com/posting-api/job-board"


class AshbyJobSourceAdapter(JobSourceAdapter):
    """Ashby public job-posting API (documented GET, unauthenticated)."""

    source = JobSource.ASHBY

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
        self._board = validate_board_site(board_token, field_name="board_site")
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

        if self._offline_fixture is not None:
            payload = json.loads(self._offline_fixture.read_text(encoding="utf-8"))
            company_name = str(payload.get("company_name") or self._board)
            board_payload = payload.get("board_payload") or payload
        elif self._live_enabled:
            company_name, board_payload = await self._fetch_live()
        else:
            raise PublicBoardCollectionError(
                PublicBoardFailureState.DISABLED,
                "Live Ashby collection disabled (ALLOW_LIVE_PUBLIC_BOARD_COLLECTION).",
            )

        if not isinstance(board_payload, dict):
            raise PublicBoardCollectionError(
                PublicBoardFailureState.INVALID_PAYLOAD,
                "Ashby board payload must be an object",
            )

        jobs, metrics = ashby_jobs_to_raw(
            board_payload,
            board_site=self._board,
            company_name=company_name,
            search_country_code=search_country,
            keyword=keyword,
            skip_ids=processed_ids,
            limit=limit,
        )
        metrics["board"] = self._board
        metrics["source"] = self.source.value

        new_processed = processed_ids | {job.source_job_id for job in jobs}
        return AdapterFetchResult(
            jobs=jobs,
            checkpoint={
                "processed_ids": sorted(new_processed),
                "board": self._board,
                "keyword": keyword.lower(),
            },
            has_more=len(jobs) >= limit,
            metrics=metrics,
        )

    async def _fetch_live(self) -> tuple[str, dict[str, Any]]:
        encoded = quote(self._board, safe="")
        url = f"{ASHBY_API}/{encoded}"
        payload = await self._http.get_json(url)
        if not isinstance(payload, dict):
            raise PublicBoardCollectionError(
                PublicBoardFailureState.INVALID_PAYLOAD,
                "Unexpected Ashby API shape",
            )
        return self._board, payload

    async def aclose(self) -> None:
        await self._http.aclose()
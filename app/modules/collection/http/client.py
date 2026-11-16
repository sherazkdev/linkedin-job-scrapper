import asyncio
import logging
from typing import Any

import httpx

from app.modules.collection.http.errors import PublicBoardCollectionError, PublicBoardFailureState
from app.modules.collection.http.hosts import DEFAULT_MAX_RESPONSE_BYTES, assert_approved_url

logger = logging.getLogger(__name__)


class PublicBoardHttpClient:
    """Bounded HTTP client for documented public job board APIs."""

    def __init__(
        self,
        *,
        timeout_seconds: float,
        min_interval_seconds: float = 1.0,
        max_response_bytes: int = DEFAULT_MAX_RESPONSE_BYTES,
        user_agent: str = "global-jobs-collector/0.1 (research; contact ops)",
    ) -> None:
        self._timeout = timeout_seconds
        self._min_interval = min_interval_seconds
        self._max_response_bytes = max_response_bytes
        self._user_agent = user_agent
        self._last_request_at: float | None = None
        self._client: httpx.AsyncClient | None = None

    async def _ensure_client(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(
                timeout=httpx.Timeout(self._timeout),
                headers={"User-Agent": self._user_agent, "Accept": "application/json"},
                follow_redirects=True,
            )
        return self._client

    async def aclose(self) -> None:
        if self._client is not None:
            await self._client.aclose()
            self._client = None

    async def _pace(self) -> None:
        if self._min_interval <= 0:
            return
        loop = asyncio.get_running_loop()
        now = loop.time()
        if self._last_request_at is not None:
            wait = self._min_interval - (now - self._last_request_at)
            if wait > 0:
                await asyncio.sleep(wait)
        self._last_request_at = loop.time()

    async def get_json(self, url: str) -> Any:
        try:
            assert_approved_url(url)
        except ValueError as exc:
            raise PublicBoardCollectionError(
                PublicBoardFailureState.INVALID_PAYLOAD,
                str(exc),
                retryable=False,
            ) from exc

        await self._pace()
        client = await self._ensure_client()
        try:
            response = await client.get(url)
        except httpx.TimeoutException as exc:
            raise PublicBoardCollectionError(
                PublicBoardFailureState.TIMEOUT,
                "Request timed out",
                retryable=True,
            ) from exc
        except httpx.HTTPError as exc:
            raise PublicBoardCollectionError(
                PublicBoardFailureState.HTTP_ERROR,
                "HTTP transport error",
                retryable=True,
            ) from exc

        return self._parse_response(response, url)

    def _parse_response(self, response: httpx.Response, url: str) -> Any:
        if len(response.content) > self._max_response_bytes:
            raise PublicBoardCollectionError(
                PublicBoardFailureState.RESPONSE_TOO_LARGE,
                "Response exceeds configured size limit",
                retryable=False,
            )

        if response.status_code == 401:
            raise PublicBoardCollectionError(
                PublicBoardFailureState.FORBIDDEN,
                "Unauthorized (401)",
                retryable=False,
            )
        if response.status_code == 403:
            raise PublicBoardCollectionError(
                PublicBoardFailureState.FORBIDDEN,
                "Forbidden (403)",
                retryable=False,
            )
        if response.status_code == 429:
            raise PublicBoardCollectionError(
                PublicBoardFailureState.RATE_LIMITED,
                "Rate limit response (429)",
                retryable=True,
            )
        if response.status_code == 404:
            raise PublicBoardCollectionError(
                PublicBoardFailureState.NOT_FOUND,
                "Resource not found (404)",
                retryable=False,
            )
        if response.status_code >= 400:
            raise PublicBoardCollectionError(
                PublicBoardFailureState.HTTP_ERROR,
                f"HTTP {response.status_code}",
                retryable=response.status_code >= 500,
            )
        try:
            return response.json()
        except ValueError as exc:
            raise PublicBoardCollectionError(
                PublicBoardFailureState.INVALID_PAYLOAD,
                "Response is not valid JSON",
            ) from exc
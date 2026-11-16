import asyncio
import logging
from dataclasses import dataclass
from typing import Any

from playwright.async_api import (
    Browser,
    BrowserContext,
    Page,
    Playwright,
    async_playwright,
)
from playwright.async_api import (
    Error as PlaywrightError,
)

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class BrowserLaunchReport:
    browser_version: str
    user_agent: str


class BrowserManager:
    """Playwright Chromium lifecycle with explicit cleanup (no identity spoofing)."""

    def __init__(
        self,
        *,
        headless: bool = True,
        launch_timeout_ms: int = 60_000,
        navigation_timeout_ms: int = 30_000,
        storage_state_path: str | None = None,
        shutdown_grace_ms: int = 15_000,
    ) -> None:
        self._headless = headless
        self._launch_timeout_ms = launch_timeout_ms
        self._navigation_timeout_ms = navigation_timeout_ms
        self._shutdown_grace_ms = shutdown_grace_ms
        self._storage_state_path = storage_state_path
        self._playwright: Playwright | None = None
        self._browser: Browser | None = None
        self._context: BrowserContext | None = None

    async def start(self) -> BrowserLaunchReport:
        if self._browser is not None:
            return self._report()
        try:
            self._playwright = await async_playwright().start()
            # --disable-dev-shm-usage: avoids Chromium /dev/shm exhaustion in Docker.
            # --no-sandbox: required for Chromium in most container runtimes (non-root browseruser);
            # acceptable only inside an isolated collector/worker container, not on a bare host.
            self._browser = await self._playwright.chromium.launch(
                headless=self._headless,
                timeout=self._launch_timeout_ms,
                args=[
                    "--disable-dev-shm-usage",
                    "--no-sandbox",
                ],
            )
            context_kwargs: dict[str, Any] = {}
            if self._storage_state_path:
                context_kwargs["storage_state"] = self._storage_state_path
            self._context = await self._browser.new_context(**context_kwargs)
            self._context.set_default_navigation_timeout(self._navigation_timeout_ms)
            self._context.set_default_timeout(self._navigation_timeout_ms)
            logger.info("Chromium launched headless=%s", self._headless)
            return self._report()
        except PlaywrightError as exc:
            logger.error("Browser launch failed: %s", exc.__class__.__name__)
            await self.shutdown()
            raise

    async def new_page(self) -> Page:
        if self._context is None:
            await self.start()
        assert self._context is not None
        return await self._context.new_page()

    def _report(self) -> BrowserLaunchReport:
        assert self._browser is not None
        version = self._browser.version
        return BrowserLaunchReport(browser_version=version, user_agent="playwright-default")

    async def shutdown(self) -> None:
        grace_s = self._shutdown_grace_ms / 1000
        logger.info("Browser shutdown event=start grace_ms=%s", self._shutdown_grace_ms)
        try:
            await asyncio.wait_for(self._shutdown_impl(), timeout=grace_s)
        except TimeoutError:
            logger.warning(
                "Browser shutdown exceeded %sms; releasing references",
                self._shutdown_grace_ms,
            )
            self._context = None
            self._browser = None
            self._playwright = None
        else:
            logger.info("Browser resources released")

    async def _shutdown_impl(self) -> None:
        if self._context is not None:
            await self._context.close()
            self._context = None
        if self._browser is not None:
            await self._browser.close()
            self._browser = None
        if self._playwright is not None:
            await self._playwright.stop()
            self._playwright = None

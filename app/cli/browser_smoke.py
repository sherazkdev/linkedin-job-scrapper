"""Chromium launch smoke test using a local HTML fixture (no network)."""

import asyncio
import logging
from pathlib import Path

from app.core.config import get_settings
from app.core.logging import configure_logging
from app.modules.collection.browser.manager import BrowserManager

logger = logging.getLogger(__name__)
# Docker image layout: package lives at /app/app
FIXTURE = Path("/app/app/modules/collection/linkedin/fixtures/search_page_1.html")


async def run_smoke() -> int:
    settings = get_settings()
    configure_logging(settings)
    if not FIXTURE.exists():
        # Local/dev path fallback
        base = Path(__file__).resolve().parents[1]
        local = base / "modules/collection/linkedin/fixtures/search_page_1.html"
        fixture = local if local.exists() else FIXTURE
    else:
        fixture = FIXTURE

    browser = BrowserManager(
        headless=settings.linkedin_browser_headless,
        launch_timeout_ms=settings.linkedin_browser_launch_timeout_ms,
        navigation_timeout_ms=settings.linkedin_navigation_timeout_ms,
    )
    try:
        report = await browser.start()
        page = await browser.new_page()
        await page.goto(fixture.as_uri(), wait_until="domcontentloaded")
        title = await page.title()
        await page.close()
        logger.info(
            "Browser smoke OK version=%s fixture=%s title=%r",
            report.browser_version,
            fixture,
            title,
        )
        return 0
    finally:
        await browser.shutdown()


def main() -> None:
    raise SystemExit(asyncio.run(run_smoke()))


if __name__ == "__main__":
    main()

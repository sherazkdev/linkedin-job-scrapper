"""Adapter rejection metrics: SERP keyword skips must not inflate post-detail keyword counters."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.core.config import Settings
from app.modules.collection.linkedin.adapter import LinkedInJobSourceAdapter


@pytest.mark.asyncio
async def test_serp_keyword_reject_does_not_increment_post_detail_keyword_mismatch() -> None:
    html_search = """
    <html><body>
    <li class="jobs-search-results__list-item">
      <a class="base-card__full-link" href="/jobs/view/9001">
        <h3 class="base-search-card__title">Product Manager</h3>
        <h4 class="base-search-card__subtitle">Acme</h4>
      </a>
    </li>
  </body></html>
    """
    settings = Settings(
        ALLOW_LIVE_LINKEDIN_COLLECTION=True,
        LINKEDIN_NAVIGATION_TIMEOUT_MS=5000,
        LINKEDIN_SELECTOR_TIMEOUT_MS=5000,
        LINKEDIN_PAGE_OPERATION_TIMEOUT_MS=5000,
        LINKEDIN_BROWSER_SHUTDOWN_GRACE_MS=1000,
    )
    browser = MagicMock()
    browser.start = AsyncMock()
    browser.new_page = AsyncMock(return_value=MagicMock())
    browser.shutdown = AsyncMock()
    adapter = LinkedInJobSourceAdapter(settings=settings, browser=browser, live_enabled=True)
    adapter._session = MagicMock()
    adapter._session.require_session = MagicMock()

    with (
        patch(
            "app.modules.collection.linkedin.adapter.capture_search_page_html",
            new=AsyncMock(
                return_value=MagicMock(
                    html=html_search,
                    page_url="https://www.linkedin.com/jobs/search/",
                    page_title="Jobs",
                    selector_timed_out=False,
                    content_timed_out=False,
                    title_timed_out=False,
                    page_unresponsive=False,
                    dom_indicators={"job_view_links": 1},
                )
            ),
        ),
        patch(
            "app.modules.collection.linkedin.adapter.close_page_bounded",
            new=AsyncMock(),
        ),
    ):
        result = await adapter.fetch_jobs(
            country_code="GB",
            keyword="software engineer",
            limit=1,
            checkpoint=None,
        )

    assert result.metrics["rejected_keyword_serp"] == 1
    assert result.metrics["rejected_keyword_mismatch"] == 0
    assert result.metrics["detail_opens"] == 0
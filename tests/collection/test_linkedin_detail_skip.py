"""Per-job detail failures must not abort the whole live fetch loop."""

from unittest.mock import AsyncMock, MagicMock, patch
from datetime import UTC, datetime

import pytest

from app.core.config import Settings
from app.modules.collection.linkedin.adapter import LinkedInJobSourceAdapter
from app.modules.collection.linkedin.errors import LinkedInCollectionError, LinkedInFailureState
from app.modules.collection.models.raw_job import RawJobRecord


@pytest.mark.asyncio
async def test_detail_unsupported_skips_card_and_continues() -> None:
    html_search = """
    <html><body>
    <li class="jobs-search-results__list-item">
      <a class="base-card__full-link" href="/jobs/view/9001">
        <h3 class="base-search-card__title">Software Engineer</h3>
        <h4 class="base-search-card__subtitle">Acme</h4>
      </a>
      <span class="job-search-card__location">Islamabad, Pakistan</span>
    </li>
    <li class="jobs-search-results__list-item">
      <a class="base-card__full-link" href="/jobs/view/9002">
        <h3 class="base-search-card__title">Software Engineer</h3>
        <h4 class="base-search-card__subtitle">Beta Co</h4>
      </a>
      <span class="job-search-card__location">Islamabad, Pakistan</span>
    </li>
    </body></html>
    """
    detail_good = """
    <html><body><div class="jobs-description__content">Build APIs daily.</div>
    <time datetime="2026-11-16T08:00:00Z">2 hours ago</time></body></html>
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

    calls = {"n": 0}

    async def capture_detail(*_args, **_kwargs):
        calls["n"] += 1
        if calls["n"] == 1:
            raise LinkedInCollectionError(
                LinkedInFailureState.UNSUPPORTED_PAGE_STRUCTURE,
                "bad detail",
            )
        return MagicMock(html=detail_good, content_timed_out=False)

    adapter = LinkedInJobSourceAdapter(
        settings=settings,
        browser=browser,
        live_enabled=True,
        filter_past_24_hours=True,
    )
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
                    dom_indicators={"job_view_links": 2},
                )
            ),
        ),
        patch(
            "app.modules.collection.linkedin.adapter.capture_job_detail_html",
            new=AsyncMock(side_effect=capture_detail),
        ),
        patch(
            "app.modules.collection.linkedin.adapter.close_page_bounded",
            new=AsyncMock(),
        ),
    ):
        result = await adapter.fetch_jobs(
            country_code="PK",
            keyword="software engineer",
            limit=1,
            checkpoint=None,
            search_location="islamabad, pakistan",
        )

    assert result.metrics["rejected_detail_error"] == 1
    assert len(result.jobs) == 1
    assert result.jobs[0].source_job_id == "9002"


@pytest.mark.asyncio
async def test_auth_block_on_detail_still_skips_without_crashing_batch() -> None:
    """Individual detail auth errors are skipped; search-level auth still fails fast."""
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
    auth_html = "<html><body>sign in to linkedin</body></html>"
    with patch(
        "app.modules.collection.linkedin.adapter.capture_search_page_html",
        new=AsyncMock(
            return_value=MagicMock(
                html=auth_html,
                page_url="https://www.linkedin.com/login",
                page_title="Login",
                selector_timed_out=False,
                content_timed_out=False,
                title_timed_out=False,
                page_unresponsive=False,
            )
        ),
        patch(
            "app.modules.collection.linkedin.adapter.close_page_bounded",
            new=AsyncMock(),
        ),
    ):
        with pytest.raises(LinkedInCollectionError) as err:
            await adapter.fetch_jobs(
                country_code="PK",
                keyword="software engineer",
                limit=1,
                checkpoint=None,
            )
    assert err.value.state == LinkedInFailureState.AUTHENTICATION_REQUIRED
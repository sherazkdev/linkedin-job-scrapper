from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.core.config import Settings
from app.modules.collection.linkedin.adapter import LinkedInJobSourceAdapter
from app.modules.collection.linkedin.errors import LinkedInCollectionError, LinkedInFailureState
from app.modules.collection.linkedin.parser import (
    search_page_is_pagination_exhausted,
)


def test_pagination_exhausted_minimal_shell_matches_smoke_diagnostics() -> None:
    html = "<html><body><div id='app'></div><p>Search</p></body></html>"
    indicators = {
        "job_view_links": 0,
        "job_cards": 0,
        "genuine_empty": False,
        "body_text_len": 264,
    }
    assert search_page_is_pagination_exhausted(html, dom_indicators=indicators) is True


def test_first_page_spa_shell_not_pagination_exhausted_without_indicators_still_unsupported() -> None:
    html = "<html><body><div id='app'></div></body></html>"
    assert search_page_is_pagination_exhausted(html) is False
    with pytest.raises(LinkedInCollectionError) as err:
        from app.modules.collection.linkedin.parser import parse_search_job_cards

        parse_search_job_cards(html, search_country_code="PK")
    assert err.value.state == LinkedInFailureState.UNSUPPORTED_PAGE_STRUCTURE


@pytest.mark.asyncio
async def test_live_search_continuation_shell_returns_pagination_end_not_error() -> None:
    page_shell = "<html><body><div id='app'></div></body></html>"
    settings = Settings(
        ALLOW_LIVE_LINKEDIN_COLLECTION=True,
        LINKEDIN_NAVIGATION_TIMEOUT_MS=5000,
        LINKEDIN_SELECTOR_TIMEOUT_MS=5000,
        LINKEDIN_PAGE_OPERATION_TIMEOUT_MS=5000,
        LINKEDIN_BROWSER_SHUTDOWN_GRACE_MS=1000,
    )
    browser = MagicMock()
    browser.new_page = AsyncMock(return_value=MagicMock())
    adapter = LinkedInJobSourceAdapter(settings=settings, browser=browser, live_enabled=True)

    capture = MagicMock(
        html=page_shell,
        page_url="https://www.linkedin.com/jobs/search/?start=50",
        page_title="Jobs",
        selector_timed_out=False,
        content_timed_out=False,
        title_timed_out=False,
        page_unresponsive=False,
        dom_indicators={
            "job_view_links": 0,
            "job_cards": 0,
            "genuine_empty": False,
            "body_text_len": 264,
        },
    )
    with patch(
        "app.modules.collection.linkedin.adapter.capture_search_page_html",
        new=AsyncMock(return_value=capture),
    ), patch(
        "app.modules.collection.linkedin.adapter.close_page_bounded",
        new=AsyncMock(),
    ):
        cards, metrics = await adapter._live_fetch_search_page_cards(
            country_code="PK",
            url="https://www.linkedin.com/jobs/search/?start=50",
            nav_ms=5000,
            op_ms=5000,
            sel_ms=5000,
            close_grace_ms=1000,
            continuation=True,
        )

    assert cards == []
    assert metrics.get("pagination_end") is True
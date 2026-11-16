import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.core.config import Settings
from app.modules.collection.factory import _linkedin_live_adapter_timeout_seconds
from app.modules.collection.linkedin.errors import LinkedInCollectionError
from app.modules.collection.linkedin.search_page_capture import (
    capture_job_detail_html,
    capture_search_page_html,
)
from app.modules.collection.linkedin.timing import PhaseTimer, duration_ms, monotonic_ms


def test_monotonic_ms_increases() -> None:
    a = monotonic_ms()
    b = monotonic_ms()
    assert b >= a


def test_duration_ms_non_negative() -> None:
    start = monotonic_ms()
    assert duration_ms(start) >= 0
    assert duration_ms(start + 1000.0) == 0


def test_phase_timer_finish_logs(caplog: pytest.LogCaptureFixture) -> None:
    import logging

    caplog.set_level(logging.INFO)
    timer = PhaseTimer(logging.getLogger("test_linkedin_timing"), phase="unit_test")
    timer.finish(event="done", sample=1)
    assert any("phase=unit_test" in r.message for r in caplog.records)


def test_linkedin_adapter_timeout_estimate_exceeds_default_collection_timeout() -> None:
    settings = Settings(
        COLLECTION_ADAPTER_TIMEOUT_SECONDS=60,
        ALLOW_LIVE_LINKEDIN_COLLECTION=True,
        LINKEDIN_MAX_LIVE_JOBS_PER_RUN=5,
        LINKEDIN_MAX_SEARCH_PAGES_PER_RUN=5,
        LINKEDIN_MAX_DETAIL_OPENS_PER_RUN=40,
    )
    budget = _linkedin_live_adapter_timeout_seconds(settings)
    assert budget > 60


@pytest.mark.asyncio
async def test_capture_job_detail_html_content_timeout_raises() -> None:
    async def slow_content() -> str:
        await asyncio.sleep(60)
        return ""

    page = MagicMock()
    page.goto = AsyncMock()
    page.content = slow_content

    with pytest.raises(LinkedInCollectionError) as err:
        await capture_job_detail_html(
            page,
            "https://www.linkedin.com/jobs/view/1",
            job_id="1",
            navigation_timeout_ms=5_000,
            operation_timeout_ms=50,
        )
    assert err.value.state.value == "navigation_timeout"


@pytest.mark.asyncio
async def test_capture_search_skips_title_content_when_unresponsive_after_selector_timeout() -> None:
    async def slow_eval(*_args, **_kwargs) -> str:
        await asyncio.sleep(60)
        return "complete"

    page = MagicMock()
    page.url = "https://www.linkedin.com/jobs/search/?keywords=x"
    page.goto = AsyncMock()
    page.wait_for_load_state = AsyncMock()
    page.wait_for_function = AsyncMock(side_effect=TimeoutError())
    page.wait_for_selector = AsyncMock(side_effect=TimeoutError())

    async def evaluate(script, *args, **kwargs):
        if script == "() => document.readyState":
            return await slow_eval()
        if "jobs/view" in script:
            return False
        if "job_view_links" in script:
            return {}
        return False

    page.evaluate = AsyncMock(side_effect=evaluate)
    page.title = AsyncMock()
    page.content = AsyncMock()

    started = asyncio.get_event_loop().time()
    capture = await capture_search_page_html(
        page,
        "https://www.linkedin.com/jobs/search/?keywords=x",
        navigation_timeout_ms=5_000,
        selector_timeout_ms=1_000,
        operation_timeout_ms=30_000,
    )
    elapsed = asyncio.get_event_loop().time() - started

    assert capture.page_unresponsive is True
    assert capture.unresponsive_reason == "js_probe_after_selector_timeout"
    assert capture.html == ""
    assert elapsed < 8
    page.title.assert_not_called()
    page.content.assert_not_called()


@pytest.mark.asyncio
async def test_capture_search_continues_snapshot_when_selector_timeout_but_page_responds() -> None:
    page = MagicMock()
    page.url = "https://www.linkedin.com/jobs/search/?keywords=x"
    page.goto = AsyncMock()
    page.wait_for_load_state = AsyncMock()
    page.wait_for_function = AsyncMock(side_effect=TimeoutError())
    page.wait_for_selector = AsyncMock(side_effect=TimeoutError())

    async def evaluate(script, *args, **kwargs):
        if "document.readyState" in script:
            return "interactive"
        if "jobs/view" in script:
            return False
        if "job_view_links" in script:
            return {"job_view_links": 0, "genuine_empty": False, "body_text_len": 100}
        return False

    page.evaluate = AsyncMock(side_effect=evaluate)
    page.title = AsyncMock(return_value="Jobs")
    page.content = AsyncMock(return_value="<html><body>ok</body></html>")

    capture = await capture_search_page_html(
        page,
        "https://www.linkedin.com/jobs/search/?keywords=x",
        navigation_timeout_ms=5_000,
        selector_timeout_ms=1_000,
        operation_timeout_ms=5_000,
    )

    assert capture.page_unresponsive is False
    assert capture.selector_timed_out is True
    assert "ok" in capture.html
    page.title.assert_called_once()
    page.content.assert_called_once()


@pytest.mark.asyncio
async def test_capture_search_hydration_restores_after_selector_timeout() -> None:
    page = MagicMock()
    page.url = "https://www.linkedin.com/jobs/search/?keywords=erp"
    page.goto = AsyncMock()
    page.wait_for_load_state = AsyncMock()
    page.wait_for_selector = AsyncMock(side_effect=TimeoutError())

    async def evaluate(script, *args, **kwargs):
        if "job_view_links" in script:
            return {
                "job_view_links": 2,
                "list_items": 0,
                "job_cards": 1,
                "genuine_empty": False,
                "ready_state": "complete",
                "body_text_len": 1200,
            }
        if "jobs/view" in script:
            return True
        return "interactive"

    page.wait_for_function = AsyncMock()
    page.evaluate = AsyncMock(side_effect=evaluate)
    page.title = AsyncMock(return_value="Jobs search")
    page.content = AsyncMock(return_value="<html><a href='/jobs/view/1'>x</a></body></html>")

    capture = await capture_search_page_html(
        page,
        "https://www.linkedin.com/jobs/search/?keywords=erp",
        navigation_timeout_ms=5_000,
        selector_timeout_ms=1_000,
        operation_timeout_ms=5_000,
    )

    assert capture.page_unresponsive is False
    assert capture.selector_timed_out is False
    assert capture.dom_indicators is not None
    assert capture.dom_indicators.get("job_view_links") == 2
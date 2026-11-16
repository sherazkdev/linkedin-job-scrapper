"""Bounded Playwright capture + safe diagnostics for LinkedIn job search pages."""

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any
from urllib.parse import parse_qs, quote, urlencode, urlparse, urlunparse

from app.modules.collection.linkedin.errors import LinkedInCollectionError, LinkedInFailureState
from app.modules.collection.linkedin.parser import (
    detect_page_state,
    parse_search_job_cards,
    search_page_diagnostics,
)
from app.modules.collection.linkedin.timing import PhaseTimer, log_phase_start

if TYPE_CHECKING:
    from playwright.async_api import Page

logger = logging.getLogger(__name__)

SEARCH_RESULTS_SELECTOR = (
    'a[href*="/jobs/view/"], li.jobs-search-results__list-item, div.job-search-card, '
    "div.job-card-container, article.job-card-container, "
    "div.base-card[data-entity-urn*='jobPosting']"
)

_JOB_LIST_HYDRATION_JS = """() => {
  const body = document.body;
  if (!body) return false;
  const lower = (body.innerText || "").toLowerCase();
  if (lower.includes("no matching jobs") || lower.includes("no results found")) {
    return true;
  }
  if (document.querySelectorAll('a[href*="/jobs/view/"]').length > 0) return true;
  const markers = document.querySelectorAll(
    "li.jobs-search-results__list-item, div.job-search-card, div.job-card-container, "
    + "article.job-card-container, ul.scaffold-layout__list-container li"
  );
  return markers.length > 0;
}"""

# After selector timeout, probe the tab before spending title/content budgets.
_PAGE_PROBE_MAX_MS = 2_000
_PAGE_PROBE_MIN_MS = 500

# Safe to echo in operator logs (search intent only).
_SAFE_QUERY_KEYS = frozenset({"keywords", "location", "start", "f_TPR", "sortBy", "geoId"})


def redact_url_for_log(url: str) -> str:
    parsed = urlparse(url)
    if not parsed.query:
        return url
    qs = parse_qs(parsed.query, keep_blank_values=True)
    redacted: list[tuple[str, str]] = []
    for key in sorted(qs):
        if key in _SAFE_QUERY_KEYS:
            for value in qs[key]:
                redacted.append((key, value))
        else:
            redacted.append((key, "[redacted]"))
    query = urlencode(redacted, quote_via=quote)
    return urlunparse(parsed._replace(query=query))


SearchPageClassification = str  # jobs | login | verification | empty | unsupported


def classify_search_page(html: str, *, search_country_code: str) -> SearchPageClassification:
    state = detect_page_state(html)
    if state in (
        LinkedInFailureState.AUTHENTICATION_REQUIRED,
        LinkedInFailureState.SESSION_EXPIRED,
    ):
        return "login"
    if state == LinkedInFailureState.VERIFICATION_REQUIRED:
        return "verification"
    diag = search_page_diagnostics(html)
    if diag["genuine_empty"]:
        return "empty"
    if state is not None:
        return "unsupported"
    try:
        cards = parse_search_job_cards(html, search_country_code=search_country_code)
    except LinkedInCollectionError as exc:
        if exc.state == LinkedInFailureState.UNSUPPORTED_PAGE_STRUCTURE:
            return "unsupported"
        return "unsupported"
    if cards:
        return "jobs"
    return "empty"


@dataclass(slots=True)
class SearchPageCapture:
    html: str
    page_url: str
    page_title: str
    selector_timed_out: bool
    content_timed_out: bool
    title_timed_out: bool
    page_unresponsive: bool = False
    unresponsive_reason: str | None = None
    dom_indicators: dict[str, Any] | None = None

    @property
    def timed_out_selector(self) -> str | None:
        return SEARCH_RESULTS_SELECTOR if self.selector_timed_out else None


@dataclass(slots=True)
class JobDetailCapture:
    html: str
    content_timed_out: bool


async def _page_responds_within(page: Page, *, probe_ms: int) -> bool:
    try:
        await asyncio.wait_for(
            page.evaluate("() => document.readyState"),
            timeout=probe_ms / 1000,
        )
        return True
    except TimeoutError:
        return False
    except Exception as exc:
        logger.debug("Search page responsiveness probe failed error=%s", exc.__class__.__name__)
        return False


def _unresponsive_probe_ms(operation_timeout_ms: int) -> int:
    tenth = max(_PAGE_PROBE_MIN_MS, operation_timeout_ms // 10)
    return min(_PAGE_PROBE_MAX_MS, tenth)


async def _read_dom_indicators(page: Page) -> dict[str, Any]:
    """Sanitized in-page counters (no cookies, no body text)."""
    try:
        raw = await page.evaluate(
            """() => {
            const body = document.body;
            const text = body ? body.innerText : "";
            const lower = text.toLowerCase();
            return {
              job_view_links: document.querySelectorAll('a[href*="/jobs/view/"]').length,
              list_items: document.querySelectorAll("li.jobs-search-results__list-item").length,
              job_cards: document.querySelectorAll(
                "div.job-search-card, div.job-card-container, article.job-card-container"
              ).length,
              scaffold_items: document.querySelectorAll(
                "ul.scaffold-layout__list-container li"
              ).length,
              ready_state: document.readyState,
              genuine_empty: lower.includes("no matching jobs") || lower.includes("no results found"),
              page_title_len: (document.title || "").length,
              body_text_len: text.length,
            };
          }"""
        )
        if isinstance(raw, dict):
            return raw
    except Exception as exc:
        logger.debug("dom indicators failed error=%s", exc.__class__.__name__)
        return {"error": exc.__class__.__name__}
    return {}


async def _wait_for_job_list_hydration(page: Page, *, budget_ms: int) -> bool:
    if budget_ms <= 0:
        return False
    try:
        await page.wait_for_function(_JOB_LIST_HYDRATION_JS, timeout=budget_ms)
        return True
    except Exception:
        pass
    deadline = time.monotonic() + (budget_ms / 1000)
    while time.monotonic() < deadline:
        try:
            ready = await page.evaluate(_JOB_LIST_HYDRATION_JS)
            if ready is True:
                return True
        except Exception:
            pass
        await asyncio.sleep(0.5)
    return False


async def capture_search_page_html(
    page: Page,
    url: str,
    *,
    navigation_timeout_ms: int,
    selector_timeout_ms: int,
    operation_timeout_ms: int,
) -> SearchPageCapture:
    """Navigate, optionally wait for results markup, then snapshot DOM with hard ceilings."""
    op_s = operation_timeout_ms / 1000
    safe_url = redact_url_for_log(url)

    nav_timer = log_phase_start(logger, "search_nav", url=safe_url)
    try:
        # commit: avoid LinkedIn SPA stalling domcontentloaded indefinitely under headless load
        await page.goto(url, wait_until="commit", timeout=navigation_timeout_ms)
    except Exception as exc:
        nav_timer.finish(event="nav_failed")
        raise LinkedInCollectionError(
            LinkedInFailureState.NAVIGATION_TIMEOUT,
            "LinkedIn search navigation failed",
            retryable=False,
        ) from exc
    nav_timer.finish(event="nav_done")

    dom_timer = log_phase_start(logger, "search_dom_load", timeout_ms=min(navigation_timeout_ms, 15_000))
    try:
        await page.wait_for_load_state("domcontentloaded", timeout=min(navigation_timeout_ms, 15_000))
        dom_timer.finish(event="domcontentloaded")
    except Exception:
        dom_timer.finish(event="domcontentloaded_timeout")

    selector_timed_out = False
    sel_timer = log_phase_start(logger, "search_wait_selector", timeout_ms=selector_timeout_ms)
    try:
        await page.wait_for_selector(SEARCH_RESULTS_SELECTOR, timeout=selector_timeout_ms)
        sel_timer.finish(event="selector_seen")
    except Exception:
        selector_timed_out = True
        sel_timer.finish(event="selector_timeout")

    hydration_budget = selector_timeout_ms if selector_timed_out else 0
    if hydration_budget > 0:
        hyd_timer = log_phase_start(logger, "search_hydration", budget_ms=hydration_budget)
        hydrated = await _wait_for_job_list_hydration(page, budget_ms=hydration_budget)
        indicators = await _read_dom_indicators(page)
        hyd_timer.finish(event="hydrated" if hydrated else "hydration_timeout", indicators=indicators)
        logger.info(
            "linkedin_collect phase=search_dom_snapshot indicators=%s url=%s",
            {k: indicators.get(k) for k in (
                "job_view_links",
                "list_items",
                "job_cards",
                "scaffold_items",
                "genuine_empty",
                "ready_state",
                "body_text_len",
            )}
            if isinstance(indicators, dict)
            else {},
            safe_url,
        )
        if hydrated:
            selector_timed_out = False

    page_url = page.url
    dom_indicators = await _read_dom_indicators(page)

    if selector_timed_out:
        probe_ms = _unresponsive_probe_ms(operation_timeout_ms)
        if not await _page_responds_within(page, probe_ms=probe_ms):
            logger.warning(
                "Search page unresponsive after selector timeout; skipping title/content probe_ms=%s",
                probe_ms,
            )
            return SearchPageCapture(
                html="",
                page_url=page_url,
                page_title="",
                selector_timed_out=True,
                content_timed_out=True,
                title_timed_out=True,
                page_unresponsive=True,
                unresponsive_reason="js_probe_after_selector_timeout",
                dom_indicators=await _read_dom_indicators(page),
            )

    title_timed_out = False
    content_timed_out = False
    title_timer = PhaseTimer(logger=logger, phase="search_page_title")
    title_timer.log(event="start")
    try:
        page_title = await asyncio.wait_for(page.title(), timeout=op_s)
        title_timer.finish(event="done")
    except TimeoutError:
        logger.warning("page.title() exceeded %sms", operation_timeout_ms)
        page_title = ""
        title_timed_out = True
        title_timer.finish(event="timeout")

    content_timer = log_phase_start(logger, "search_html_capture", operation_timeout_ms=operation_timeout_ms)
    try:
        html = await asyncio.wait_for(page.content(), timeout=op_s)
        content_timer.finish(event="done", html_length=len(html))
    except TimeoutError:
        logger.warning("page.content() exceeded %sms", operation_timeout_ms)
        html = ""
        content_timed_out = True
        content_timer.finish(event="timeout")

    return SearchPageCapture(
        html=html,
        page_url=page_url,
        page_title=page_title,
        selector_timed_out=selector_timed_out,
        content_timed_out=content_timed_out,
        title_timed_out=title_timed_out,
        dom_indicators=dom_indicators,
    )


async def capture_job_detail_html(
    page: Page,
    url: str,
    *,
    job_id: str,
    navigation_timeout_ms: int,
    operation_timeout_ms: int,
) -> JobDetailCapture:
    """Navigate to a job detail page and snapshot DOM with hard ceilings."""
    op_s = operation_timeout_ms / 1000
    safe_url = redact_url_for_log(url)

    nav_timer = log_phase_start(logger, "detail_nav", job_id=job_id, url=safe_url)
    try:
        await page.goto(url, wait_until="commit", timeout=navigation_timeout_ms)
    except Exception as exc:
        nav_timer.finish(event="nav_failed")
        raise LinkedInCollectionError(
            LinkedInFailureState.NAVIGATION_TIMEOUT,
            f"LinkedIn job detail navigation failed for {job_id}",
            retryable=False,
        ) from exc
    nav_timer.finish(event="nav_done")

    content_timer = log_phase_start(
        logger,
        "detail_html_capture",
        job_id=job_id,
        operation_timeout_ms=operation_timeout_ms,
    )
    try:
        html = await asyncio.wait_for(page.content(), timeout=op_s)
        content_timer.finish(event="done", html_length=len(html))
        return JobDetailCapture(html=html, content_timed_out=False)
    except TimeoutError:
        logger.warning("detail page.content() exceeded %sms job_id=%s", operation_timeout_ms, job_id)
        content_timer.finish(event="timeout")
        raise LinkedInCollectionError(
            LinkedInFailureState.NAVIGATION_TIMEOUT,
            f"LinkedIn job detail content capture timed out for {job_id}",
            retryable=False,
        )
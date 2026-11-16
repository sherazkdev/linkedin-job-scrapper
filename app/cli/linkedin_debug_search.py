"""One-off search page diagnostics (no secrets in output). Operator use only."""

import argparse
import asyncio

from app.core.config import get_settings
from app.core.logging import configure_logging
from app.modules.collection.browser.manager import BrowserManager
from app.modules.collection.linkedin.browser_page import close_page_bounded
from app.modules.collection.linkedin.adapter import _build_search_url
from app.modules.collection.linkedin.location_filter import resolve_search_location
from app.modules.collection.linkedin.parser import parse_search_job_cards, search_page_diagnostics
from app.modules.collection.linkedin.search_page_capture import (
    SEARCH_RESULTS_SELECTOR,
    capture_search_page_html,
    classify_search_page,
    redact_url_for_log,
)

def _print_diagnostics(
    *,
    capture_url: str,
    requested_url: str,
    page_title: str,
    html: str,
    country: str,
    selector_timed_out: bool,
    content_timed_out: bool,
    title_timed_out: bool,
    page_unresponsive: bool,
) -> None:
    print(f"requested_url={redact_url_for_log(requested_url)}")
    print(f"page_url={redact_url_for_log(capture_url)}")
    print(f"page_title={page_title!r}")
    if selector_timed_out:
        print("wait_selector=timeout")
        print(f"timed_out_selector={SEARCH_RESULTS_SELECTOR}")
    else:
        print("wait_selector=ok")
    if content_timed_out:
        print("page_content=timeout")
    if title_timed_out:
        print("page_title_fetch=timeout")
    print(f"html_length={len(html)}")
    if page_unresponsive:
        print("page_unresponsive=true")
    if not html:
        print("classification=unsupported")
        print("results_parsed=false")
        return

    classification = classify_search_page(html, search_country_code=country)
    diag = search_page_diagnostics(html)
    print(f"classification={classification}")
    print(
        "job_counts="
        f"list_items={diag['list_items']},"
        f"job_search_cards={diag['job_search_cards']},"
        f"base_cards={diag['base_cards']},"
        f"job_view_links={diag['job_view_links']}"
    )
    print(f"genuine_empty={diag['genuine_empty']}")
    results_parsed = False
    cards_count = 0
    if classification == "jobs":
        try:
            cards = parse_search_job_cards(html, search_country_code=country)
            cards_count = len(cards)
            results_parsed = cards_count > 0
            if cards:
                print(f"first_title={cards[0]['title'][:80]}")
                print(f"first_location={cards[0].get('location_text')}")
        except Exception as exc:
            print(f"parse_error={exc.__class__.__name__}: {exc}")
    print(f"cards_parsed={cards_count}")
    print(f"results_parsed={str(results_parsed).lower()}")


async def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--country", default="PK")
    parser.add_argument("--keyword", default="Software Engineer")
    parser.add_argument("--location", default="Islamabad, Pakistan")
    args = parser.parse_args()
    settings = get_settings()
    configure_logging(settings)
    loc = resolve_search_location(args.country, args.location)
    url = _build_search_url(
        keyword=args.keyword,
        location=loc,
        start=0,
        past_24h=True,
        sort_recent=True,
    )
    browser = BrowserManager(
        headless=settings.linkedin_browser_headless,
        launch_timeout_ms=settings.linkedin_browser_launch_timeout_ms,
        navigation_timeout_ms=settings.linkedin_navigation_timeout_ms,
        storage_state_path=settings.linkedin_storage_state_path,
        shutdown_grace_ms=settings.linkedin_browser_shutdown_grace_ms,
    )
    await browser.start()
    page = await browser.new_page()
    try:
        capture = await capture_search_page_html(
            page,
            url,
            navigation_timeout_ms=settings.linkedin_navigation_timeout_ms,
            selector_timeout_ms=settings.linkedin_selector_timeout_ms,
            operation_timeout_ms=settings.linkedin_page_operation_timeout_ms,
        )
        _print_diagnostics(
            capture_url=capture.page_url,
            requested_url=url,
            page_title=capture.page_title,
            html=capture.html,
            country=args.country,
            selector_timed_out=capture.selector_timed_out,
            content_timed_out=capture.content_timed_out,
            title_timed_out=capture.title_timed_out,
            page_unresponsive=capture.page_unresponsive,
        )
    finally:
        await close_page_bounded(page, grace_ms=settings.linkedin_browser_shutdown_grace_ms)
        await browser.shutdown()


if __name__ == "__main__":
    asyncio.run(main())
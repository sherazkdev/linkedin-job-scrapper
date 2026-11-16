import logging
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any
from urllib.parse import quote_plus

from app.core.config import Settings
from app.modules.collection.adapters.base import AdapterFetchResult, JobSourceAdapter

if TYPE_CHECKING:
    from app.modules.collection.browser.manager import BrowserManager
from app.modules.collection.linkedin.errors import LinkedInCollectionError, LinkedInFailureState
from app.modules.collection.linkedin.location_filter import (
    job_matches_search_location,
    resolve_search_location,
)
from app.modules.collection.linkedin.parser import (
    detect_page_state,
    parse_job_detail_html,
    parse_search_job_cards,
    search_page_diagnostics,
)
from app.modules.collection.linkedin.browser_page import close_page_bounded
from app.modules.collection.linkedin.search_page_capture import (
    capture_job_detail_html,
    capture_search_page_html,
    classify_search_page,
)
from app.modules.collection.linkedin.timing import log_phase_start
from app.modules.collection.linkedin.keyword_relevance import title_matches_keyword
from app.modules.collection.linkedin.recency import (
    build_recency_rejection_diagnostic,
    is_within_past_24_hours,
)
from app.modules.collection.linkedin.session import LinkedInSessionStore
from app.modules.collection.models.raw_job import RawJobRecord
from app.modules.jobs.models.job import JobSource

logger = logging.getLogger(__name__)


class LinkedInJobSourceAdapter(JobSourceAdapter):
    source = JobSource.LINKEDIN

    def __init__(
        self,
        *,
        settings: Settings,
        browser: "BrowserManager | None" = None,
        offline_html_root: Path | None = None,
        live_enabled: bool = False,
        filter_past_24_hours: bool = False,
    ) -> None:
        self._settings = settings
        self._browser = browser
        self._offline_root = offline_html_root
        self._live_enabled = live_enabled
        self._filter_past_24h = filter_past_24_hours
        self._session = LinkedInSessionStore(settings.linkedin_storage_state_path)

    async def fetch_jobs(
        self,
        *,
        country_code: str,
        keyword: str,
        limit: int,
        checkpoint: dict[str, Any] | None,
        search_location: str | None = None,
    ) -> AdapterFetchResult:
        page_index = int((checkpoint or {}).get("page_index", 0))
        processed_ids: set[str] = set((checkpoint or {}).get("processed_ids", []))

        if self._offline_root is not None:
            return await self._fetch_from_fixtures(
                country_code=country_code,
                keyword=keyword,
                limit=limit,
                page_index=page_index,
                processed_ids=processed_ids,
            )

        if not self._live_enabled:
            raise LinkedInCollectionError(
                LinkedInFailureState.ACCESS_DENIED,
                "Live LinkedIn collection disabled (set ALLOW_LIVE_LINKEDIN_COLLECTION=true).",
            )
        return await self._fetch_live(
            country_code=country_code,
            keyword=keyword,
            limit=limit,
            page_index=page_index,
            processed_ids=processed_ids,
            search_location=search_location,
        )

    async def _fetch_from_fixtures(
        self,
        *,
        country_code: str,
        keyword: str,
        limit: int,
        page_index: int,
        processed_ids: set[str],
    ) -> AdapterFetchResult:
        assert self._offline_root is not None
        search_path = self._offline_root / f"search_page_{page_index + 1}.html"
        if not search_path.exists():
            if page_index == 0:
                raise LinkedInCollectionError(
                    LinkedInFailureState.NO_RESULTS,
                    "Offline search fixture missing",
                )
            return AdapterFetchResult(
                jobs=[],
                checkpoint={"page_index": page_index, "processed_ids": list(processed_ids)},
                has_more=False,
            )

        html = search_path.read_text(encoding="utf-8")
        cards = parse_search_job_cards(html, search_country_code=country_code)
        if not cards:
            raise LinkedInCollectionError(
                LinkedInFailureState.NO_RESULTS,
                "No jobs in search fixture",
            )

        jobs: list[RawJobRecord] = []
        for card in cards:
            if len(jobs) >= limit:
                break
            job_id = str(card["source_job_id"])
            if job_id in processed_ids:
                continue
            detail_path = self._offline_root / f"job_detail_{job_id}.html"
            if not detail_path.exists():
                raise LinkedInCollectionError(
                    LinkedInFailureState.UNSUPPORTED_PAGE_STRUCTURE,
                    f"Missing detail fixture for job {job_id}",
                )
            detail_html = detail_path.read_text(encoding="utf-8")
            jobs.append(parse_job_detail_html(detail_html, card=card))
            processed_ids.add(job_id)

        next_page = page_index + 1
        has_more = (self._offline_root / f"search_page_{next_page + 1}.html").exists()
        checkpoint_page = next_page if jobs else page_index
        checkpoint = {
            "page_index": checkpoint_page,
            "processed_ids": list(processed_ids),
            "keyword": keyword.lower(),
        }
        return AdapterFetchResult(
            jobs=jobs,
            checkpoint=checkpoint,
            has_more=has_more and len(jobs) >= limit,
        )

    async def _fetch_live(
        self,
        *,
        country_code: str,
        keyword: str,
        limit: int,
        page_index: int,
        processed_ids: set[str],
        search_location: str | None,
    ) -> AdapterFetchResult:
        self._session.require_session()
        if self._browser is None:
            raise LinkedInCollectionError(
                LinkedInFailureState.ACCESS_DENIED,
                "Browser manager not configured for live collection",
            )
        live_timer = log_phase_start(logger, "live_fetch")
        await self._browser.start()
        location = resolve_search_location(country_code, search_location)
        start = page_index * 25
        url = _build_search_url(
            keyword=keyword,
            location=location,
            start=start,
            past_24h=self._filter_past_24h,
            sort_recent=True,
        )
        nav_ms = self._settings.linkedin_navigation_timeout_ms
        op_ms = self._settings.linkedin_page_operation_timeout_ms
        sel_ms = self._settings.linkedin_selector_timeout_ms
        close_grace_ms = self._settings.linkedin_browser_shutdown_grace_ms

        page_timer = log_phase_start(logger, "search_new_page")
        page = await self._browser.new_page()
        page_timer.finish()
        try:
            capture = await capture_search_page_html(
                page,
                url,
                navigation_timeout_ms=nav_ms,
                selector_timeout_ms=sel_ms,
                operation_timeout_ms=op_ms,
            )
            if capture.page_unresponsive:
                state = (
                    LinkedInFailureState.JS_PROBE_TIMEOUT
                    if capture.unresponsive_reason == "js_probe_after_selector_timeout"
                    else LinkedInFailureState.PAGE_UNRESPONSIVE
                )
                raise LinkedInCollectionError(
                    state,
                    "LinkedIn search page unresponsive during capture",
                    retryable=False,
                )
            if capture.selector_timed_out:
                logger.warning(
                    "Search results selector not seen before parse; continuing dom_indicators=%s",
                    capture.dom_indicators,
                )
            elif capture.dom_indicators:
                logger.info(
                    "Search capture dom_indicators=%s",
                    {k: capture.dom_indicators.get(k) for k in (
                        "job_view_links",
                        "list_items",
                        "job_cards",
                        "genuine_empty",
                    )},
                )
            if capture.content_timed_out:
                raise LinkedInCollectionError(
                    LinkedInFailureState.NAVIGATION_TIMEOUT,
                    "LinkedIn search HTML capture timed out",
                    retryable=False,
                )
            html = capture.html
        except LinkedInCollectionError:
            raise
        except Exception as exc:
            raise LinkedInCollectionError(
                LinkedInFailureState.NAVIGATION_TIMEOUT,
                "LinkedIn search navigation failed",
                retryable=False,
            ) from exc
        finally:
            close_timer = log_phase_start(logger, "search_page_close")
            await close_page_bounded(page, grace_ms=close_grace_ms)
            close_timer.finish()

        class_timer = log_phase_start(logger, "search_classification")
        classification = classify_search_page(html, search_country_code=country_code)
        class_timer.finish(classification=classification)

        page_state = detect_page_state(html)
        if page_state is not None:
            raise LinkedInCollectionError(
                page_state,
                f"LinkedIn search blocked: {page_state.value}",
            )
        cards_timer = log_phase_start(logger, "search_cards_parse")
        cards = parse_search_job_cards(html, search_country_code=country_code)
        cards_timer.finish(cards_count=len(cards))
        if not cards:
            diag = search_page_diagnostics(html)
            logger.warning("LinkedIn search empty diagnostics=%s", diag)
            msg = "LinkedIn reported zero matching jobs for this search"
            if self._filter_past_24h:
                msg += " (past 24h URL filter f_TPR=r86400 is active)"
            if not diag.get("genuine_empty"):
                msg += "; page lacked recognizable results markup"
            raise LinkedInCollectionError(LinkedInFailureState.NO_RESULTS, msg)

        jobs: list[RawJobRecord] = []
        metrics: dict[str, Any] = {
            "rejected_stale": 0,
            "rejected_unknown_posting": 0,
            "rejected_location_mismatch": 0,
            "rejected_keyword_mismatch": 0,
            "rejection_diagnostics": [],
            "filter_past_24_hours": self._filter_past_24h,
            "search_location": location,
        }
        now = datetime.now(UTC)
        for card in cards:
            if len(jobs) >= limit:
                break
            job_id = str(card["source_job_id"])
            if job_id in processed_ids:
                continue
            detail_page = await self._browser.new_page()
            try:
                detail_capture = await capture_job_detail_html(
                    detail_page,
                    card["job_url"],
                    job_id=job_id,
                    navigation_timeout_ms=nav_ms,
                    operation_timeout_ms=op_ms,
                )
                detail_html = detail_capture.html
            finally:
                await close_page_bounded(detail_page, grace_ms=close_grace_ms)
            parse_timer = log_phase_start(logger, "detail_posting_parse", job_id=job_id)
            raw = parse_job_detail_html(detail_html, card=card, strict_posting_time=False)
            parse_timer.finish()
            filter_timer = log_phase_start(logger, "detail_recency_location", job_id=job_id)
            if search_location and not job_matches_search_location(
                raw.location_text or card.get("location_text"),
                location,
            ):
                filter_timer.finish(outcome="rejected_location_mismatch")
                metrics["rejected_location_mismatch"] += 1
                metrics["rejection_diagnostics"].append(
                    build_recency_rejection_diagnostic(
                        source_job_id=job_id,
                        title=card.get("title"),
                        posting_label=card.get("posted_text") or raw.posting_time_text,
                        posted_at=raw.posted_at,
                        now=now,
                        reason="location_mismatch",
                    )
                )
                continue
            job_title = raw.title or card.get("title")
            if not title_matches_keyword(job_title, keyword):
                filter_timer.finish(outcome="rejected_keyword_mismatch")
                metrics["rejected_keyword_mismatch"] += 1
                metrics["rejection_diagnostics"].append(
                    build_recency_rejection_diagnostic(
                        source_job_id=job_id,
                        title=job_title,
                        posting_label=card.get("posted_text") or raw.posting_time_text,
                        posted_at=raw.posted_at,
                        now=now,
                        reason="keyword_mismatch",
                    )
                )
                continue
            if self._filter_past_24h:
                recency = is_within_past_24_hours(raw.posted_at, reference=now)
                if recency is False:
                    filter_timer.finish(outcome="rejected_stale")
                    metrics["rejected_stale"] += 1
                    diag = build_recency_rejection_diagnostic(
                        source_job_id=job_id,
                        title=card.get("title"),
                        posting_label=card.get("posted_text") or raw.posting_time_text,
                        posted_at=raw.posted_at,
                        now=now,
                        reason="stale",
                    )
                    metrics["rejection_diagnostics"].append(diag)
                    logger.info("LinkedIn job rejected stale diagnostic=%s", diag)
                    continue
                if recency is None:
                    filter_timer.finish(outcome="rejected_unknown_posting")
                    metrics["rejected_unknown_posting"] += 1
                    metrics["rejection_diagnostics"].append(
                        build_recency_rejection_diagnostic(
                            source_job_id=job_id,
                            title=card.get("title"),
                            posting_label=card.get("posted_text") or raw.posting_time_text,
                            posted_at=raw.posted_at,
                            now=now,
                            reason="unknown_posting_time",
                        )
                    )
                    continue
            filter_timer.finish(outcome="accepted")
            jobs.append(raw)
            processed_ids.add(job_id)

        live_timer.finish(jobs_collected=len(jobs))
        checkpoint = {
            "page_index": page_index + 1,
            "processed_ids": list(processed_ids),
            "keyword": keyword.lower(),
        }
        return AdapterFetchResult(
            jobs=jobs,
            checkpoint=checkpoint,
            has_more=len(cards) > len(jobs),
            metrics=metrics,
        )

    async def shutdown_browser(self) -> None:
        if self._browser is not None:
            shutdown_timer = log_phase_start(logger, "browser_shutdown")
            await self._browser.shutdown()
            shutdown_timer.finish()


def _build_search_url(
    *,
    keyword: str,
    location: str,
    start: int,
    past_24h: bool,
    sort_recent: bool = False,
) -> str:
    params = f"keywords={quote_plus(keyword)}&location={quote_plus(location)}&start={start}"
    if past_24h:
        params += "&f_TPR=r86400"
    if sort_recent:
        params += "&sortBy=DD"
    return f"https://www.linkedin.com/jobs/search/?{params}"

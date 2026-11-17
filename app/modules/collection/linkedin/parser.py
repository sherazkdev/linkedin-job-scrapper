import re
from typing import Any
from urllib.parse import parse_qs, urlparse

from bs4 import BeautifulSoup

from app.modules.collection.linkedin.errors import LinkedInCollectionError, LinkedInFailureState
from app.modules.collection.linkedin.pagination import LINKEDIN_SEARCH_PAGE_SIZE
from app.modules.collection.models.raw_job import RawJobRecord
from app.modules.jobs.posting_time import parse_posting_time

_JOB_ID_NUMERIC = re.compile(r"/jobs/view/(?P<id>\d+)(?:[/?#]|$)")
_JOB_ID_SLUG = re.compile(r"/jobs/view/[^/?#]+-(?P<id>\d+)(?:[/?#]|$)")
_JOB_URN_PATTERN = re.compile(r"urn:li:jobPosting:(?P<id>\d+)")


_VERIFICATION_CHALLENGE_URL = re.compile(
    r"(?:https?://)?(?:[\w-]+\.)?linkedin\.com/checkpoint/challenge|/checkpoint/challenge(?:[/?#\"']|$)",
    re.IGNORECASE,
)


def _html_looks_like_job_search_results(lowered_html: str) -> bool:
    return "/jobs/view/" in lowered_html and (
        "jobs-search-results__list-item" in lowered_html
        or "job-search-card" in lowered_html
        or "job-card-container" in lowered_html
        or "scaffold-layout__list-container" in lowered_html
        or "jobs-search__results-list" in lowered_html
        or "data-occludable-job-id" in lowered_html
        or "base-search-card__title" in lowered_html
    )


def detect_page_state(html: str) -> LinkedInFailureState | None:
    lowered = html.lower()
    if "authwall" in lowered or "sign in to linkedin" in lowered or 'id="username"' in lowered:
        return LinkedInFailureState.AUTHENTICATION_REQUIRED
    if _VERIFICATION_CHALLENGE_URL.search(html) and not _html_looks_like_job_search_results(lowered):
        return LinkedInFailureState.VERIFICATION_REQUIRED
    if "session expired" in lowered or "your session has expired" in lowered:
        return LinkedInFailureState.SESSION_EXPIRED
    if "rate limit" in lowered or "too many requests" in lowered:
        return LinkedInFailureState.RATE_LIMITED
    if "access denied" in lowered or "403" in lowered and "forbidden" in lowered:
        return LinkedInFailureState.ACCESS_DENIED
    return None


def dedupe_and_cap_search_cards(cards: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """One card per job; LinkedIn SERP offset increments by 25."""
    seen: set[str] = set()
    unique: list[dict[str, Any]] = []
    for card in cards:
        job_id = str(card["source_job_id"])
        if job_id in seen:
            continue
        seen.add(job_id)
        unique.append(card)
        if len(unique) >= LINKEDIN_SEARCH_PAGE_SIZE:
            break
    return unique


def parse_search_job_cards(html: str, *, search_country_code: str) -> list[dict[str, Any]]:
    state = detect_page_state(html)
    if state is not None:
        raise LinkedInCollectionError(state, f"LinkedIn page state: {state.value}")

    soup = BeautifulSoup(html, "html.parser")
    cards = soup.select("li.jobs-search-results__list-item")
    if not cards:
        cards = soup.select(
            "ul.jobs-search__results-list li, div.jobs-search-results-list__list-item"
        )
    if not cards:
        cards = soup.select(
            "div.job-search-card, div.job-card-container, article.job-card-container, "
            "div.base-card, [data-occludable-job-id]"
        )
    if not cards:
        return dedupe_and_cap_search_cards(
            _finalize_search_cards(soup, items=[], search_country_code=search_country_code)
        )

    items: list[dict[str, Any]] = []
    for card in cards:
        link = card.select_one(
            "a.base-card__full-link, a.job-card-list__title, a[href*='/jobs/view/']"
        )
        if link is None:
            continue
        href = link.get("href", "")
        job_id = _extract_job_id(href) or _extract_job_id_from_urn(card)
        if not job_id:
            continue
        title_el = card.select_one(
            ".base-search-card__title, .job-card-list__title, "
            ".job-card-container__link, h3"
        )
        company_el = card.select_one(
            ".base-search-card__subtitle, .job-card-container__primary-description, h4"
        )
        location_el = card.select_one(
            ".job-search-card__location, .job-card-container__metadata-item, "
            ".job-card-container__metadata-wrapper"
        )
        time_el = card.select_one("time[datetime], time")
        if title_el is None or company_el is None:
            continue
        items.append(
            {
                "source_job_id": job_id,
                "title": title_el.get_text(" ", strip=True),
                "company": company_el.get_text(" ", strip=True),
                "location_text": location_el.get_text(" ", strip=True) if location_el else None,
                "search_country_code": search_country_code.upper(),
                "job_url": _absolute_job_url(href),
                "posted_hint": time_el.get("datetime") if time_el else None,
                "posted_text": time_el.get_text(" ", strip=True) if time_el else None,
            }
        )
    if not items:
        fallback = _parse_cards_from_job_links(soup, search_country_code=search_country_code)
        if fallback:
            return dedupe_and_cap_search_cards(fallback)
        raise LinkedInCollectionError(
            LinkedInFailureState.UNSUPPORTED_PAGE_STRUCTURE,
            "Search results present but required job card fields missing",
        )
    return dedupe_and_cap_search_cards(items)


def search_page_is_pagination_exhausted(
    html: str,
    *,
    dom_indicators: dict[str, Any] | None = None,
) -> bool:
    """True when a later SERP offset has no jobs (not auth/block).

    LinkedIn often returns a minimal SPA shell when ``start`` is past the last result.
    """
    if detect_page_state(html) is not None:
        return False
    diag = search_page_diagnostics(html)
    if diag.get("genuine_empty"):
        return True
    indicators = dom_indicators or {}
    if indicators.get("genuine_empty"):
        return True
    job_links = int(indicators.get("job_view_links", diag.get("job_view_links", 0)))
    if job_links > 0:
        return False
    body_len = int(indicators.get("body_text_len", 0))
    if body_len <= 0:
        soup = BeautifulSoup(html, "html.parser")
        body_len = len(soup.get_text(" ", strip=True))
    has_list_markup = any(
        int(diag.get(key, 0)) > 0
        for key in (
            "list_items",
            "job_search_cards",
            "job_card_containers",
            "jobs_search_results",
            "occludable_jobs",
            "base_cards",
        )
    )
    if has_list_markup:
        return False
    if 0 < body_len < 600:
        return True
    return False


def search_page_diagnostics(html: str) -> dict[str, int | bool]:
    soup = BeautifulSoup(html, "html.parser")
    return {
        "list_items": len(soup.select("li.jobs-search-results__list-item")),
        "job_search_cards": len(soup.select("div.job-search-card")),
        "job_card_containers": len(
            soup.select("div.job-card-container, article.job-card-container")
        ),
        "scaffold_items": len(soup.select("ul.scaffold-layout__list-container li")),
        "jobs_search_results": len(
            soup.select("ul.jobs-search__results-list li, div.jobs-search-results-list__list-item")
        ),
        "occludable_jobs": len(soup.select("[data-occludable-job-id]")),
        "base_cards": len(soup.select("div.base-card")),
        "job_view_links": len(soup.select('a[href*="/jobs/view/"]')),
        "genuine_empty": _is_genuine_empty_results(soup),
    }


def _is_genuine_empty_results(soup: BeautifulSoup) -> bool:
    text = soup.get_text(" ", strip=True).lower()
    return "no matching jobs" in text or "no results found" in text


def _count_job_view_links(soup: BeautifulSoup) -> int:
    return len(soup.select('a[href*="/jobs/view/"]'))


def _finalize_search_cards(
    soup: BeautifulSoup,
    *,
    items: list[dict[str, Any]],
    search_country_code: str,
) -> list[dict[str, Any]]:
    if items:
        return dedupe_and_cap_search_cards(items)
    fallback = _parse_cards_from_job_links(soup, search_country_code=search_country_code)
    if fallback:
        return dedupe_and_cap_search_cards(fallback)
    if _is_genuine_empty_results(soup):
        return []
    if _count_job_view_links(soup) > 0:
        raise LinkedInCollectionError(
            LinkedInFailureState.UNSUPPORTED_PAGE_STRUCTURE,
            "Job links present but search card markup not recognized",
        )
    raise LinkedInCollectionError(
        LinkedInFailureState.UNSUPPORTED_PAGE_STRUCTURE,
        "Search page missing job list markup (possible SPA shell or incomplete load)",
    )


def _parse_cards_from_job_links(
    soup: BeautifulSoup,
    *,
    search_country_code: str,
) -> list[dict[str, Any]]:
    seen: set[str] = set()
    items: list[dict[str, Any]] = []
    for link in soup.select('a[href*="/jobs/view/"]'):
        href = link.get("href", "")
        parent = link.find_parent(["li", "div"])
        card_root = parent if parent is not None else link
        job_id = _extract_job_id(href) or _extract_job_id_from_urn(card_root)
        if not job_id or job_id in seen:
            continue
        seen.add(job_id)
        title = link.get_text(" ", strip=True) or None
        company_el = None
        location_el = None
        if parent is not None:
            company_el = parent.select_one(
                ".base-search-card__subtitle, .job-card-container__primary-description, h4"
            )
            location_el = parent.select_one(
                ".job-search-card__location, .job-card-container__metadata-item"
            )
        if not title:
            title_el = card_root.select_one("h3, .job-card-list__title")
            title = title_el.get_text(" ", strip=True) if title_el else None
        if not title:
            continue
        company_name = company_el.get_text(" ", strip=True) if company_el else ""
        if not company_name:
            continue
        items.append(
            {
                "source_job_id": job_id,
                "title": title,
                "company": company_name,
                "location_text": location_el.get_text(" ", strip=True) if location_el else None,
                "search_country_code": search_country_code.upper(),
                "job_url": _absolute_job_url(href),
                "posted_hint": None,
                "posted_text": None,
            }
        )
    return items


def parse_job_detail_html(
    html: str,
    *,
    card: dict[str, Any],
    strict_posting_time: bool = True,
) -> RawJobRecord:
    state = detect_page_state(html)
    if state is not None:
        raise LinkedInCollectionError(state, f"LinkedIn detail page state: {state.value}")

    soup = BeautifulSoup(html, "html.parser")
    desc_el = soup.select_one(
        ".jobs-description__content, .jobs-box__html-content, #job-details, .show-more-less-html"
    )
    if desc_el is None:
        raise LinkedInCollectionError(
            LinkedInFailureState.UNSUPPORTED_PAGE_STRUCTURE,
            "Job detail page missing description selector",
        )
    description = desc_el.get_text("\n", strip=True)
    if not description:
        raise LinkedInCollectionError(
            LinkedInFailureState.UNSUPPORTED_PAGE_STRUCTURE,
            "Job description empty",
        )

    workplace = _extract_workplace(soup)
    employment = _extract_employment(soup)
    city = _parse_city_from_location(card.get("location_text"))
    posted_at, posting_label = parse_posting_time(
        iso_hint=card.get("posted_hint"),
        relative_text=card.get("posted_text"),
    )
    if posted_at is None and strict_posting_time:
        raise LinkedInCollectionError(
            LinkedInFailureState.UNSUPPORTED_PAGE_STRUCTURE,
            "Posting date missing (not manufactured)",
        )

    return RawJobRecord(
        source_job_id=str(card["source_job_id"]),
        title=str(card["title"]),
        company=str(card["company"]),
        search_country_code=str(card["search_country_code"]),
        location_text=card.get("location_text"),
        city=city,
        description=description,
        job_url=str(card["job_url"]),
        employment_type=employment,
        workplace_type=workplace,
        posted_at=posted_at,
        posting_time_text=card.get("posted_text") or posting_label,
        posting_time_iso_hint=card.get("posted_hint"),
    )


def _extract_job_id(href: str) -> str | None:
    for pattern in (_JOB_ID_NUMERIC, _JOB_ID_SLUG):
        match = pattern.search(href)
        if match:
            return match.group("id")
    parsed = urlparse(href)
    query = parse_qs(parsed.query)
    current = query.get("currentJobId", [])
    return current[0] if current else None


def _extract_job_id_from_urn(card: Any) -> str | None:
    urn = card.get("data-entity-urn")
    if not urn:
        return None
    match = _JOB_URN_PATTERN.search(urn)
    return match.group("id") if match else None


def _absolute_job_url(href: str) -> str:
    if href.startswith("http"):
        return href
    return f"https://www.linkedin.com{href}"


def _parse_city_from_location(location_text: str | None) -> str | None:
    if not location_text:
        return None
    return location_text.split(",")[0].strip() or None


def _extract_workplace(soup: BeautifulSoup) -> str | None:
    text = soup.get_text(" ", strip=True).lower()
    if "remote" in text:
        return "remote"
    if "hybrid" in text:
        return "hybrid"
    if "on-site" in text or "onsite" in text:
        return "on_site"
    return None


def _extract_employment(soup: BeautifulSoup) -> str | None:
    selector = (
        ".job-details-jobs-unified-top-card__job-insight span, "
        ".description__job-criteria-item"
    )
    for label in soup.select(selector):
        text = label.get_text(" ", strip=True).lower()
        if "full-time" in text or "full time" in text:
            return "full_time"
        if "part-time" in text or "part time" in text:
            return "part_time"
        if "contract" in text:
            return "contract"
        if "internship" in text:
            return "internship"
    return None



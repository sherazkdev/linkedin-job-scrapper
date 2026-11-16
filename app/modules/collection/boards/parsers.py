import re
from datetime import UTC, datetime
from html import unescape
from typing import Any

from bs4 import BeautifulSoup

from app.modules.collection.boards.validation import scoped_source_job_id
from app.modules.collection.models.raw_job import RawJobRecord


def _strip_html(html: str | None) -> str:
    if not html:
        return ""
    text = BeautifulSoup(html, "html.parser").get_text(separator=" ")
    return re.sub(r"\s+", " ", unescape(text)).strip()


def _parse_iso_datetime(value: str | None) -> datetime | None:
    if not value:
        return None
    normalized = value.replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def _keyword_match(title: str, keyword: str) -> bool:
    if keyword in {"*", "_all", "all"}:
        return True
    return keyword.lower() in title.lower()


def _greenhouse_first_published(row: dict[str, Any]) -> tuple[datetime | None, str | None]:
    first = row.get("first_published")
    if isinstance(first, str) and first.strip():
        parsed = _parse_iso_datetime(first.strip())
        if parsed is not None:
            return parsed, first.strip()
    return None, None


def _greenhouse_updated_at(row: dict[str, Any]) -> datetime | None:
    updated = row.get("updated_at")
    if isinstance(updated, str) and updated.strip():
        return _parse_iso_datetime(updated.strip())
    return None


def _map_ashby_workplace(row: dict[str, Any]) -> str | None:
    workplace = str(row.get("workplaceType") or "").strip()
    mapping = {"OnSite": "on_site", "Remote": "remote", "Hybrid": "hybrid"}
    if workplace in mapping:
        return mapping[workplace]
    if row.get("isRemote"):
        return "remote"
    return None


def greenhouse_jobs_to_raw(
    payload: dict[str, Any],
    *,
    board_site: str,
    company_name: str,
    search_country_code: str,
    keyword: str,
    skip_ids: set[str],
    limit: int,
) -> tuple[list[RawJobRecord], dict[str, int]]:
    jobs = payload.get("jobs")
    if not isinstance(jobs, list):
        raise ValueError("Greenhouse payload missing jobs array")

    metrics = {
        "listings_seen": len(jobs),
        "keyword_rejected": 0,
        "duplicate_skipped": 0,
        "missing_description": 0,
        "missing_posted_at": 0,
        "incomplete_skipped": 0,
        "unlisted_skipped": 0,
    }
    records: list[RawJobRecord] = []

    for row in jobs:
        if len(records) >= limit:
            break
        if not isinstance(row, dict):
            continue
        job_id = row.get("id")
        title = str(row.get("title") or "").strip()
        if job_id is None or not title:
            metrics["incomplete_skipped"] += 1
            continue
        source_job_id = scoped_source_job_id(board_site, str(job_id))
        if source_job_id in skip_ids:
            metrics["duplicate_skipped"] += 1
            continue
        if not _keyword_match(title, keyword):
            metrics["keyword_rejected"] += 1
            continue

        location = row.get("location") if isinstance(row.get("location"), dict) else {}
        location_text = str(location.get("name") or "").strip() or None
        content = _strip_html(str(row.get("content") or ""))
        description_provided = bool(content)
        if not content:
            metrics["missing_description"] += 1

        posted_at, posted_hint = _greenhouse_first_published(row)
        source_updated_at = _greenhouse_updated_at(row)
        if posted_at is None:
            metrics["missing_posted_at"] += 1

        workplace = None
        if location_text and "remote" in location_text.lower():
            workplace = "remote"

        absolute_url = str(row.get("absolute_url") or "").strip()
        if not absolute_url.startswith("https://"):
            metrics["incomplete_skipped"] += 1
            continue

        records.append(
            RawJobRecord(
                source_job_id=source_job_id,
                title=title,
                company=company_name,
                search_country_code=search_country_code,
                location_text=location_text,
                description=content,
                description_provided=description_provided,
                job_url=absolute_url,
                workplace_type=workplace,
                posted_at=posted_at,
                source_updated_at=source_updated_at,
                posting_time_iso_hint=posted_hint,
            )
        )

    metrics["valid_listings"] = len(records)
    return records, metrics


def lever_postings_to_raw(
    postings: list[Any],
    *,
    board_site: str,
    company_name: str,
    search_country_code: str,
    keyword: str,
    skip_ids: set[str],
    limit: int,
) -> tuple[list[RawJobRecord], dict[str, int]]:
    metrics = {
        "listings_seen": len(postings),
        "keyword_rejected": 0,
        "duplicate_skipped": 0,
        "missing_description": 0,
        "missing_posted_at": 0,
        "incomplete_skipped": 0,
        "unlisted_skipped": 0,
    }
    records: list[RawJobRecord] = []

    for row in postings:
        if len(records) >= limit:
            break
        if not isinstance(row, dict):
            continue
        if row.get("state") and str(row.get("state")).lower() not in {"published", "open"}:
            metrics["unlisted_skipped"] += 1
            continue
        provider_id = str(row.get("id") or "").strip()
        title = str(row.get("text") or "").strip()
        if not provider_id or not title:
            metrics["incomplete_skipped"] += 1
            continue
        source_job_id = scoped_source_job_id(board_site, provider_id)
        if source_job_id in skip_ids:
            metrics["duplicate_skipped"] += 1
            continue
        if not _keyword_match(title, keyword):
            metrics["keyword_rejected"] += 1
            continue

        categories = row.get("categories") if isinstance(row.get("categories"), dict) else {}
        location_text = str(categories.get("location") or "").strip() or None
        description = str(row.get("descriptionPlain") or row.get("description") or "").strip()
        if description:
            description = _strip_html(description)
        description_provided = bool(description)
        if not description:
            metrics["missing_description"] += 1

        created = row.get("createdAt")
        posted_at = None
        posted_hint = None
        if isinstance(created, int | float):
            posted_at = datetime.fromtimestamp(created / 1000.0, tz=UTC)
            posted_hint = str(int(created))
        elif isinstance(created, str):
            posted_at = _parse_iso_datetime(created)
            posted_hint = created
        if posted_at is None:
            metrics["missing_posted_at"] += 1

        hosted = str(row.get("hostedUrl") or row.get("applyUrl") or "").strip()
        if not hosted.startswith("https://"):
            metrics["incomplete_skipped"] += 1
            continue

        workplace = None
        if location_text and "remote" in location_text.lower():
            workplace = "remote"

        records.append(
            RawJobRecord(
                source_job_id=source_job_id,
                title=title,
                company=company_name,
                search_country_code=search_country_code,
                location_text=location_text,
                description=description,
                description_provided=description_provided,
                job_url=hosted,
                workplace_type=workplace,
                posted_at=posted_at,
                posting_time_iso_hint=posted_hint,
            )
        )

    metrics["valid_listings"] = len(records)
    return records, metrics


def ashby_jobs_to_raw(
    payload: dict[str, Any],
    *,
    board_site: str,
    company_name: str,
    search_country_code: str,
    keyword: str,
    skip_ids: set[str],
    limit: int,
) -> tuple[list[RawJobRecord], dict[str, int]]:
    postings = payload.get("jobs") or payload.get("jobPostings")
    if not isinstance(postings, list):
        raise ValueError("Ashby payload missing jobs array")

    metrics = {
        "listings_seen": len(postings),
        "keyword_rejected": 0,
        "duplicate_skipped": 0,
        "missing_description": 0,
        "missing_posted_at": 0,
        "incomplete_skipped": 0,
        "unlisted_skipped": 0,
    }
    records: list[RawJobRecord] = []

    for row in postings:
        if len(records) >= limit:
            break
        if not isinstance(row, dict):
            continue
        if row.get("isListed") is False:
            metrics["unlisted_skipped"] += 1
            continue
        provider_id = str(row.get("id") or "").strip()
        title = str(row.get("title") or "").strip()
        if not provider_id or not title:
            metrics["incomplete_skipped"] += 1
            continue
        source_job_id = scoped_source_job_id(board_site, provider_id)
        if source_job_id in skip_ids:
            metrics["duplicate_skipped"] += 1
            continue
        if not _keyword_match(title, keyword):
            metrics["keyword_rejected"] += 1
            continue

        location_text = str(row.get("location") or row.get("locationName") or "").strip() or None
        description = str(row.get("descriptionPlain") or "").strip()
        if not description:
            description = _strip_html(str(row.get("descriptionHtml") or ""))
        description_provided = bool(description)
        if not description:
            metrics["missing_description"] += 1

        published = row.get("publishedAt")
        posted_at = _parse_iso_datetime(str(published)) if published is not None else None
        if posted_at is None:
            metrics["missing_posted_at"] += 1

        apply_url = str(row.get("applyUrl") or row.get("jobUrl") or "").strip()
        if not apply_url.startswith("https://"):
            metrics["incomplete_skipped"] += 1
            continue

        workplace = _map_ashby_workplace(row)

        records.append(
            RawJobRecord(
                source_job_id=source_job_id,
                title=title,
                company=company_name,
                search_country_code=search_country_code,
                location_text=location_text,
                description=description,
                description_provided=description_provided,
                job_url=apply_url,
                workplace_type=workplace,
                posted_at=posted_at,
                posting_time_iso_hint=str(published) if published is not None else None,
            )
        )

    metrics["valid_listings"] = len(records)
    return records, metrics
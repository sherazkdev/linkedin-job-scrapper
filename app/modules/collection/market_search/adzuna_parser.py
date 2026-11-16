"""Parse Adzuna job search JSON into RawJobRecord (no fabricated fields)."""

from datetime import UTC, datetime
from typing import Any

from app.modules.collection.models.raw_job import RawJobRecord

_ADZUNA_ID_PREFIX = "adzuna"


def _parse_created(value: str | None) -> datetime | None:
    if not value or not isinstance(value, str):
        return None
    normalized = value.replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def _keyword_matches(title: str, keyword: str) -> bool:
    kw = keyword.strip().lower()
    if not kw or kw == "*":
        return True
    return kw in title.lower()


def adzuna_results_to_raw(
    payload: dict[str, Any],
    *,
    adzuna_country_slug: str,
    search_country_code: str,
    keyword: str,
    skip_ids: set[str],
    limit: int,
) -> tuple[list[RawJobRecord], dict[str, Any]]:
    results = payload.get("results")
    if not isinstance(results, list):
        return [], {"listings_seen": 0, "accepted": 0, "rejected": 0}

    accepted: list[RawJobRecord] = []
    rejected = 0
    for row in results:
        if not isinstance(row, dict):
            rejected += 1
            continue
        raw_id = row.get("id")
        if raw_id is None:
            rejected += 1
            continue
        source_job_id = f"{_ADZUNA_ID_PREFIX}:{adzuna_country_slug}:{raw_id}"
        if source_job_id in skip_ids:
            continue
        title = str(row.get("title") or "").strip()
        if not title:
            rejected += 1
            continue
        if not _keyword_matches(title, keyword):
            continue
        company_block = row.get("company")
        company = ""
        if isinstance(company_block, dict):
            company = str(company_block.get("display_name") or "").strip()
        if not company:
            rejected += 1
            continue
        job_url = str(row.get("redirect_url") or row.get("url") or "").strip()
        if not job_url.startswith("http"):
            rejected += 1
            continue
        location_block = row.get("location")
        location_text: str | None = None
        if isinstance(location_block, dict):
            location_text = location_block.get("display_name")
            if location_text is not None:
                location_text = str(location_text).strip() or None
        description = str(row.get("description") or "").strip()
        created = _parse_created(row.get("created"))
        accepted.append(
            RawJobRecord(
                source_job_id=source_job_id,
                title=title,
                company=company,
                search_country_code=search_country_code.upper(),
                country_code=None,
                location_text=location_text,
                description=description,
                description_provided=bool(description),
                job_url=job_url,
                posted_at=created,
                posting_time_iso_hint=(
                    row.get("created") if isinstance(row.get("created"), str) else None
                ),
            )
        )
        if len(accepted) >= limit:
            break

    metrics = {
        "listings_seen": len(results),
        "accepted": len(accepted),
        "rejected": rejected,
        "adzuna_country_slug": adzuna_country_slug,
    }
    return accepted, metrics
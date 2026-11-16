import hashlib
import re
from datetime import UTC, datetime, timedelta
from typing import Any

from app.modules.collection.adapters.base import AdapterFetchResult, JobSourceAdapter
from app.modules.collection.models.raw_job import RawJobRecord
from app.modules.jobs.models.job import JobSource

FIXTURE_COMPANIES = (
    "Northwind Collective",
    "Atlas Fictional Systems",
    "Harborline Analytics",
    "Summit Relay Labs",
)


def _slug(value: str) -> str:
    value = value.strip().lower()
    value = re.sub(r"[^a-z0-9]+", "-", value)
    return value.strip("-") or "role"


class FixtureJobSourceAdapter(JobSourceAdapter):
    """Generates fictional listings for pipeline verification (no external I/O)."""

    source = JobSource.FIXTURE

    async def fetch_jobs(
        self,
        *,
        country_code: str,
        keyword: str,
        limit: int,
        checkpoint: dict[str, Any] | None,
        search_location: str | None = None,
    ) -> AdapterFetchResult:
        offset = int((checkpoint or {}).get("offset", 0))
        remaining = max(limit, 0)
        jobs: list[RawJobRecord] = []
        idx = offset
        keyword_slug = _slug(keyword)
        country = country_code.upper()

        fictional_locations = {
            "DE": ("Berlin", "Germany"),
            "SE": ("Stockholm", "Sweden"),
            "US": ("Austin", "United States"),
            "GB": ("London", "United Kingdom"),
            "PK": ("Karachi", "Pakistan"),
        }
        city, place = fictional_locations.get(country, ("Sample City", country))
        location_text = f"{city}, {place}"

        while remaining > 0 and idx < offset + limit + 3:
            company = FIXTURE_COMPANIES[idx % len(FIXTURE_COMPANIES)]
            source_job_id = f"fixture-{country.lower()}-{keyword_slug}-{idx:04d}"
            title = f"{keyword.title()} ({country}) #{idx + 1}"
            digest = hashlib.sha256(source_job_id.encode()).hexdigest()[:12]
            jobs.append(
                RawJobRecord(
                    source_job_id=source_job_id,
                    title=title,
                    company=company,
                    search_country_code=country,
                    location_text=location_text,
                    city=city,
                    description=(
                        f"Fictional {keyword} role at {company}. "
                        f"Reference id {digest}. Not a real opening."
                    ),
                    job_url=f"https://example.org/careers/{country.lower()}/{keyword_slug}/{idx}",
                    employment_type="full_time",
                    workplace_type="hybrid",
                    posted_at=datetime.now(UTC) - timedelta(days=(idx % 5) + 1),
                )
            )
            idx += 1
            remaining -= 1

        next_checkpoint = {"offset": idx, "keyword": keyword.lower(), "country_code": country}
        has_more = idx < offset + limit + 10
        return AdapterFetchResult(jobs=jobs, checkpoint=next_checkpoint, has_more=has_more)

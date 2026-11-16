from datetime import UTC, datetime
from uuid import uuid4

import httpx
import pytest

from app.database.mongodb import get_mongodb
from app.modules.jobs.models.job import (
    EmploymentType,
    JobDocument,
    JobSource,
    JobStatus,
    WorkplaceType,
)
from app.modules.jobs.repositories.job_repository import JobRepository


@pytest.mark.asyncio
async def test_country_code_filters_actual_job_country_only(
    async_client: httpx.AsyncClient,
    require_integration: None,
) -> None:
    repo = JobRepository(get_mongodb().database)
    now = datetime.now(UTC)
    suffix = uuid4().hex[:8]
    jobs = [
        JobDocument(
            source=JobSource.DEMO,
            source_job_id=f"geo-us-de-{suffix}",
            title=f"Backend {suffix}",
            company="Acme",
            search_country_code="US",
            country_code="DE",
            location_text="Berlin, Germany",
            city="Berlin",
            description="Searched US market, job in Germany",
            employment_type=EmploymentType.FULL_TIME,
            workplace_type=WorkplaceType.HYBRID,
            job_url="https://example.org/geo-us-de",
            posted_at=now,
            first_seen_at=now,
            last_seen_at=now,
            status=JobStatus.ACTIVE,
        ),
        JobDocument(
            source=JobSource.DEMO,
            source_job_id=f"geo-us-us-{suffix}",
            title=f"SRE {suffix}",
            company="Acme",
            search_country_code="US",
            country_code="US",
            location_text="Austin, United States",
            city="Austin",
            description="US job",
            employment_type=EmploymentType.FULL_TIME,
            workplace_type=WorkplaceType.REMOTE,
            job_url="https://example.org/geo-us-us",
            posted_at=now,
            first_seen_at=now,
            last_seen_at=now,
            status=JobStatus.ACTIVE,
        ),
    ]
    for job in jobs:
        await repo.upsert_job(job)

    by_actual = await async_client.get(
        "/api/v1/jobs",
        params={"country_code": "US", "q": suffix, "page_size": 50},
    )
    assert by_actual.status_code == 200
    items = by_actual.json()["data"]["items"]
    assert all(i.get("country_code") == "US" for i in items)
    assert not any(i["source_job_id"] == f"geo-us-de-{suffix}" for i in items)

    by_market = await async_client.get(
        "/api/v1/jobs",
        params={"search_country_code": "US", "q": suffix, "page_size": 50},
    )
    assert by_market.status_code == 200
    markets = by_market.json()["data"]["items"]
    assert any(i["source_job_id"] == f"geo-us-de-{suffix}" for i in markets)
    assert any(i["source_job_id"] == f"geo-us-us-{suffix}" for i in markets)


@pytest.mark.asyncio
async def test_list_excludes_description(
    async_client: httpx.AsyncClient,
    require_integration: None,
) -> None:
    response = await async_client.get("/api/v1/jobs", params={"page_size": 1})
    assert response.status_code == 200
    item = response.json()["data"]["items"][0]
    assert "description" not in item


@pytest.mark.asyncio
async def test_jobs_stats_and_countries(
    async_client: httpx.AsyncClient,
    require_integration: None,
) -> None:
    stats = await async_client.get("/api/v1/jobs/stats")
    assert stats.status_code == 200
    payload = stats.json()["data"]
    assert "total_active" in payload
    assert "by_job_country" in payload
    assert "by_search_market" in payload

    countries = await async_client.get("/api/v1/countries")
    assert countries.status_code == 200
    assert "job_countries" in countries.json()["data"]
    assert "search_markets" in countries.json()["data"]
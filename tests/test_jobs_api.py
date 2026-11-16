from datetime import UTC, datetime

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
async def test_jobs_pagination_and_country_filter(
    async_client: httpx.AsyncClient,
    require_integration: None,
) -> None:
    repo = JobRepository(get_mongodb().database)
    now = datetime.now(UTC)
    for idx, country in enumerate(["DE", "DE", "FR"]):
        job = JobDocument(
            source=JobSource.DEMO,
            source_job_id=f"pagination-test-{idx}",
            title=f"Role {idx}",
            company="Test GmbH",
            search_country_code=country,
            country_code=country,
            location_text=f"Berlin, {country}",
            city="Berlin",
            description="Test job",
            employment_type=EmploymentType.FULL_TIME,
            workplace_type=WorkplaceType.REMOTE,
            job_url=f"https://example.org/{idx}",
            posted_at=now,
            first_seen_at=now,
            last_seen_at=now,
            status=JobStatus.ACTIVE,
        )
        await repo.upsert_job(job)

    page1 = await async_client.get("/api/v1/jobs", params={"page": 1, "page_size": 2})
    assert page1.status_code == 200
    data = page1.json()["data"]
    assert data["page"] == 1
    assert data["page_size"] == 2
    assert len(data["items"]) <= 2
    assert data["total"] >= 2

    filtered = await async_client.get("/api/v1/jobs", params={"country_code": "DE"})
    assert filtered.status_code == 200
    items = filtered.json()["data"]["items"]
    assert all(item["country_code"] == "DE" for item in items)


@pytest.mark.asyncio
async def test_get_job_by_id(
    async_client: httpx.AsyncClient,
    require_integration: None,
) -> None:
    repo = JobRepository(get_mongodb().database)
    now = datetime.now(UTC)
    job = JobDocument(
        source=JobSource.DEMO,
        source_job_id="get-by-id-test",
        title="SRE",
        company="Acme",
        search_country_code="US",
        country_code="US",
        location_text="Austin, United States",
        city="Austin",
        description="Ops role",
        employment_type=EmploymentType.FULL_TIME,
        workplace_type=WorkplaceType.HYBRID,
        job_url="https://example.org/sre",
        posted_at=now,
        first_seen_at=now,
        last_seen_at=now,
        status=JobStatus.ACTIVE,
    )
    doc, _ = await repo.upsert_job(job)
    job_id = str(doc["_id"])

    response = await async_client.get(f"/api/v1/jobs/{job_id}")
    assert response.status_code == 200
    assert response.json()["data"]["id"] == job_id
    assert response.json()["data"]["title"] == "SRE"

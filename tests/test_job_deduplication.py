from datetime import UTC, datetime
from uuid import uuid4

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
async def test_unique_source_job_deduplication(integration_db: None) -> None:
    repo = JobRepository(get_mongodb().database)
    now = datetime.now(UTC)
    source_job_id = f"dedup-test-{uuid4().hex[:12]}"
    base = JobDocument(
        source=JobSource.DEMO,
        source_job_id=source_job_id,
        title="Original Title",
        company="Acme",
        search_country_code="NL",
        country_code="NL",
        location_text="Amsterdam, Netherlands",
        city="Amsterdam",
        description="First version",
        employment_type=EmploymentType.FULL_TIME,
        workplace_type=WorkplaceType.REMOTE,
        job_url="https://example.org/dedup",
        posted_at=now,
        first_seen_at=now,
        last_seen_at=now,
        status=JobStatus.ACTIVE,
    )
    first_doc, created = await repo.upsert_job(base)
    assert created is True

    updated = base.model_copy(update={"title": "Updated Title", "description": "Second version"})
    second_doc, created_again = await repo.upsert_job(updated)
    assert created_again is False
    assert str(first_doc["_id"]) == str(second_doc["_id"])
    assert second_doc["title"] == "Updated Title"

    total = await get_mongodb().database["jobs"].count_documents(
        {"source": JobSource.DEMO.value, "sourceJobId": source_job_id}
    )
    assert total == 1

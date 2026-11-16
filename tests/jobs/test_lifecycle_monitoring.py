from datetime import UTC, datetime, timedelta

import pytest

from app.database.temp_database import open_database
from app.modules.collection.models.enums import JobUpsertOutcome
from app.modules.jobs.models.job import (
    EmploymentType,
    JobDocument,
    JobSource,
    JobStatus,
    WorkplaceType,
)
from app.modules.jobs.repositories.job_repository import JobRepository
from app.modules.jobs.services.lifecycle import JobLifecycleService
from app.modules.operations.monitoring import build_operations_snapshot


@pytest.mark.asyncio
async def test_stale_candidates_dry_run_only(integration_db: None) -> None:
    async with open_database("global_jobs_test") as database:
        lifecycle = JobLifecycleService(database)
        result = await lifecycle.apply_stale_status(not_seen_days=90, dry_run=True)
        assert result["updated"] == 0


@pytest.mark.asyncio
async def test_reactivate_on_unchanged_seen(integration_db: None) -> None:
    now = datetime.now(UTC)
    async with open_database("global_jobs_test") as database:
        repo = JobRepository(database)
        sid = "lifecycle-reactivate-1"
        job = JobDocument(
            source=JobSource.DEMO,
            source_job_id=sid,
            title="Role",
            company="Acme",
            search_country_code="DE",
            country_code="DE",
            location_text="Berlin, Germany",
            description="desc",
            employment_type=EmploymentType.FULL_TIME,
            workplace_type=WorkplaceType.REMOTE,
            job_url="https://example.org/lc",
            posted_at=now,
            first_seen_at=now,
            last_seen_at=now - timedelta(days=10),
            status=JobStatus.ACTIVE,
        )
        await repo.upsert_job_tracked(job)
        await database["jobs"].update_one(
            {"sourceJobId": sid},
            {"$set": {"status": JobStatus.STALE.value}},
        )
        observe = job.model_copy(update={"last_seen_at": now})
        outcome_doc, outcome = await repo.upsert_job_tracked(observe)
        assert outcome in {JobUpsertOutcome.UNCHANGED, JobUpsertOutcome.UPDATED}
        assert outcome_doc["status"] == JobStatus.ACTIVE.value


@pytest.mark.asyncio
async def test_monitoring_snapshot(integration_db: None) -> None:
    async with open_database("global_jobs_test") as database:
        snap = await build_operations_snapshot(database)
        assert "jobs" in snap
        assert "collection" in snap
        assert snap["jobs"]["total"] >= 0
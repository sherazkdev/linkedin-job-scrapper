from datetime import UTC, datetime, timedelta

import pytest

from app.modules.jobs.models.job import JobStatus
from app.modules.jobs.public_visibility import (
    is_publicly_listable,
    mongo_public_max_age_clause,
    posting_date_unknown,
)
from app.modules.jobs.schemas.filters import JobListFilters, JobSort, build_mongo_query
from app.modules.jobs.services.lifecycle import JobLifecycleService


def test_engineer_developer_keyword_equivalence_imported_elsewhere() -> None:
    assert posting_date_unknown({"posted_at": None, "first_seen_at": datetime.now(UTC)})


def test_public_listing_age_uses_posted_at_not_last_seen() -> None:
    now = datetime.now(UTC)
    doc = {
        "status": JobStatus.ACTIVE.value,
        "posted_at": now - timedelta(days=8),
        "first_seen_at": now,
        "last_seen_at": now,
    }
    assert not is_publicly_listable(doc, max_age_days=7, now=now)


def test_public_listing_fallback_first_seen_when_no_posted_at() -> None:
    now = datetime.now(UTC)
    doc = {
        "status": JobStatus.ACTIVE.value,
        "posted_at": None,
        "first_seen_at": now - timedelta(days=2),
    }
    assert is_publicly_listable(doc, max_age_days=7, now=now)


def test_mongo_public_max_age_clause_structure() -> None:
    clause = mongo_public_max_age_clause(max_age_days=7)
    assert "$or" in clause


def test_build_mongo_query_applies_max_age_for_active() -> None:
    q = build_mongo_query(
        JobListFilters(status=JobStatus.ACTIVE, sort=JobSort.POSTED_AT_DESC),
        public_listing_max_age_days=7,
    )
    assert "$and" in q


@pytest.mark.asyncio
async def test_expiry_idempotent(integration_db: None) -> None:
    from app.database.temp_database import open_database

    now = datetime.now(UTC)
    async with open_database("global_jobs_test") as database:
        await database["jobs"].insert_one(
            {
                "source": "linkedin",
                "sourceJobId": "exp-1",
                "title": "Old Role",
                "company": "Co",
                "search_country_code": "US",
                "status": JobStatus.ACTIVE.value,
                "posted_at": now - timedelta(days=10),
                "first_seen_at": now - timedelta(days=10),
                "last_seen_at": now,
                "employment_type": "full_time",
                "workplace_type": "remote",
                "job_url": "https://example.org/j",
            }
        )
        svc = JobLifecycleService(database)
        preview = await svc.apply_public_listing_expiry(max_age_days=7, dry_run=True, limit=50)
        assert preview["candidates"] >= 1
        first = await svc.apply_public_listing_expiry(
            max_age_days=7, dry_run=False, limit=50, batch_id="b1"
        )
        second = await svc.apply_public_listing_expiry(
            max_age_days=7, dry_run=False, limit=50, batch_id="b2"
        )
        assert first["updated"] >= 1
        assert second["updated"] == 0
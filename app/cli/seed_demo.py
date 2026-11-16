"""
Idempotent demo job seeder. Run manually only; never auto-run in production.

Usage: python -m app.cli.seed_demo
"""

import asyncio
import logging
from datetime import UTC, datetime, timedelta

from app.core.config import get_settings
from app.core.logging import configure_logging
from app.database.indexes import ensure_job_indexes
from app.database.mongodb import get_mongodb
from app.modules.jobs.models.job import (
    EmploymentType,
    JobDataProvenance,
    JobDocument,
    JobSource,
    JobStatus,
    WorkplaceType,
)
from app.modules.jobs.repositories.job_repository import JobRepository

logger = logging.getLogger(__name__)

DEMO_JOBS: list[dict] = [
    {
        "source_job_id": "demo-001",
        "title": "Backend Engineer",
        "company": "Nordic Data Labs",
        "country_code": "SE",
        "city": "Stockholm",
        "description": "Build APIs and data pipelines for a fictional analytics product.",
        "employment_type": EmploymentType.FULL_TIME,
        "workplace_type": WorkplaceType.HYBRID,
        "job_url": "https://example.org/jobs/demo-001",
        "days_ago": 3,
    },
    {
        "source_job_id": "demo-002",
        "title": "Platform SRE",
        "company": "Maple Cloud Cooperative",
        "country_code": "CA",
        "city": "Toronto",
        "description": "Operate container platforms and observability stacks (fictional).",
        "employment_type": EmploymentType.FULL_TIME,
        "workplace_type": WorkplaceType.REMOTE,
        "job_url": "https://example.org/jobs/demo-002",
        "days_ago": 1,
    },
    {
        "source_job_id": "demo-003",
        "title": "Data Engineer",
        "company": "Rio Analytics",
        "country_code": "BR",
        "city": "São Paulo",
        "description": "Design batch and streaming jobs for synthetic market data.",
        "employment_type": EmploymentType.CONTRACT,
        "workplace_type": WorkplaceType.ON_SITE,
        "job_url": "https://example.org/jobs/demo-003",
        "days_ago": 7,
    },
]


async def run_seed() -> int:
    settings = get_settings()
    configure_logging(settings)

    if settings.is_production and not settings.allow_demo_seed:
        logger.error(
            "Refusing to seed demo data in production (set ALLOW_DEMO_SEED=true to override)"
        )
        return 1

    mongodb = get_mongodb()
    await mongodb.connect()
    await ensure_job_indexes(mongodb.database)
    repo = JobRepository(mongodb.database)

    now = datetime.now(UTC)
    created = 0
    updated = 0
    for row in DEMO_JOBS:
        posted = now - timedelta(days=row["days_ago"])
        cc = row["country_code"]
        job = JobDocument(
            source=JobSource.DEMO,
            source_job_id=row["source_job_id"],
            title=row["title"],
            company=row["company"],
            search_country_code=cc,
            country_code=cc,
            location_text=f"{row['city']}, {cc}",
            city=row["city"],
            description=row["description"],
            employment_type=row["employment_type"],
            workplace_type=row["workplace_type"],
            job_url=row["job_url"],
            posted_at=posted,
            first_seen_at=now,
            last_seen_at=now,
            status=JobStatus.ACTIVE,
            data_provenance=JobDataProvenance.DEMO_SEED,
        )
        _, was_created = await repo.upsert_job(job)
        if was_created:
            created += 1
        else:
            updated += 1

    await mongodb.disconnect()
    logger.info("Demo seed complete created=%s updated=%s", created, updated)
    return 0


def main() -> None:
    raise SystemExit(asyncio.run(run_seed()))


if __name__ == "__main__":
    main()

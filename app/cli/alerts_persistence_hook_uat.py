"""Pilot-only: JobPersistenceService.persist_jobs → AlertProcessor (synthetic jobs)."""

from __future__ import annotations

import asyncio
import json
import os
import uuid
from datetime import UTC, datetime

from app.core.config import get_settings
from app.database.temp_database import open_database
from app.modules.alerts.constants import TEST_SUBSCRIBER_TAG
from app.modules.alerts.repositories import NotificationRepository, SavedSearchRepository
from app.modules.collection.factory import _build_persistence
from app.modules.jobs.models.job import (
    EmploymentType,
    JobDataProvenance,
    JobDocument,
    JobSource,
    JobStatus,
)


def _job(suffix: str, *, title: str, status: JobStatus = JobStatus.ACTIVE) -> JobDocument:
    now = datetime.now(UTC)
    return JobDocument(
        source=JobSource.FIXTURE,
        source_job_id=f"uat-persist-hook-{suffix}",
        title=title,
        company="UAT Hook",
        search_country_code="PK",
        country_code="PK",
        city="Islamabad",
        employment_type=EmploymentType.FULL_TIME,
        job_url=f"https://example.invalid/{suffix}",
        posted_at=now,
        first_seen_at=now,
        last_seen_at=now,
        status=status,
        data_provenance=JobDataProvenance.SYNTHETIC_FIXTURE,
    )


async def _notif_count(notif: NotificationRepository, sub: str) -> int:
    _, total, _ = await notif.list_for_subscriber(subscriber_id=sub, page=1, page_size=1)
    return total


async def run() -> dict:
    os.environ["ALERTS_MATCHING_ENABLED"] = "true"
    os.environ["MONGO_DB_NAME"] = "global_jobs_pilot"
    get_settings.cache_clear()
    settings = get_settings()

    async with open_database("global_jobs_pilot") as db:
        sub_a = str(uuid.uuid4())
        sub_b = str(uuid.uuid4())
        for sid in (sub_a, sub_b):
            await db.alert_subscribers.insert_one(
                {
                    "subscriber_id": sid,
                    "token_hash": f"uat-hook-{sid}",
                    "purpose": TEST_SUBSCRIBER_TAG,
                    "created_at": datetime.now(UTC),
                }
            )
        searches = SavedSearchRepository(db)
        await searches.create(
            subscriber_id=sub_a,
            payload={"q": "HookTest", "country_code": "PK", "alerts_enabled": True},
        )
        await searches.create(
            subscriber_id=sub_b,
            payload={"q": "Other", "country_code": "CA", "alerts_enabled": True},
        )

        persistence = _build_persistence(db, settings)
        notif = NotificationRepository(db)

        await persistence.persist_jobs([_job("1", title="HookTest Engineer Role")])
        n_create = await _notif_count(notif, sub_a)
        n_b = await _notif_count(notif, sub_b)

        await persistence.persist_jobs([_job("1", title="HookTest Engineer Role")])
        n_dup = await _notif_count(notif, sub_a)

        await persistence.persist_jobs([_job("1", title="HookTest Engineer Role Updated")])
        n_update = await _notif_count(notif, sub_a)

        await persistence.persist_jobs([_job("1", title="HookTest Engineer Role Updated", status=JobStatus.CLOSED)])
        await persistence.persist_jobs([_job("1", title="HookTest Engineer Role Updated", status=JobStatus.ACTIVE)])
        n_react = await _notif_count(notif, sub_a)

        return {
            "after_create": n_create,
            "subscriber_b": n_b,
            "after_unchanged": n_dup,
            "after_update": n_update,
            "after_reactivate": n_react,
            "isolation_ok": n_b == 0 and n_create >= 1,
            "dedupe_ok": n_dup <= n_create,
        }


def main() -> None:
    print(json.dumps(asyncio.run(run()), indent=2))


if __name__ == "__main__":
    main()
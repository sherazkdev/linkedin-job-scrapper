"""Pilot-only alert UAT (synthetic jobs + integration-tagged subscribers)."""

from __future__ import annotations

import argparse
import asyncio
import logging
import os
import uuid
from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

from app.core.config import get_settings
from app.database.temp_database import open_database
from app.modules.alerts.constants import TEST_SUBSCRIBER_TAG
from app.modules.alerts.digest import DailyDigestService
from app.modules.alerts.processor import AlertProcessor
from app.modules.alerts.repositories import (
    DigestDeliveryRepository,
    DigestStateRepository,
    NotificationRepository,
    SavedSearchRepository,
)
from app.modules.collection.models.enums import JobUpsertOutcome
from app.modules.jobs.models.job import EmploymentType, JobStatus
from app.modules.jobs.repositories.job_repository import JobRepository

logger = logging.getLogger(__name__)

SYNTHETIC_SOURCE = "integration_test"
SYNTHETIC_PREFIX = "uat-alert-job-"


async def _insert_synthetic_job(database, *, suffix: str, title: str, country: str, **extra) -> dict:
    now = datetime.now(UTC)
    doc = {
        "source": SYNTHETIC_SOURCE,
        "sourceJobId": f"{SYNTHETIC_PREFIX}{suffix}",
        "title": title,
        "company": "Pilot UAT Corp",
        "country_code": country,
        "search_country_code": country,
        "city": "Islamabad",
        "status": JobStatus.ACTIVE.value,
        "employment_type": EmploymentType.FULL_TIME.value,
        "is_remote": False,
        "posted_at": now - timedelta(hours=1),
        "first_seen_at": now - timedelta(hours=1),
        "last_seen_at": now,
        "job_url": f"https://example.invalid/jobs/{suffix}",
        "integration_test": True,
        **extra,
    }
    await database.jobs.update_one(
        {"source": doc["source"], "sourceJobId": doc["sourceJobId"]},
        {"$set": doc},
        upsert=True,
    )
    saved = await database.jobs.find_one(
        {"source": doc["source"], "sourceJobId": doc["sourceJobId"]}
    )
    if saved is None:
        raise RuntimeError("synthetic job missing after upsert")
    return saved


async def run_uat() -> dict:
    os.environ["ALERTS_MATCHING_ENABLED"] = "true"
    os.environ["ALERTS_DIGEST_ENABLED"] = "true"
    get_settings.cache_clear()
    settings = get_settings()
    if settings.mongo_db_name != "global_jobs_pilot":
        raise SystemExit("UAT requires MONGO_DB_NAME=global_jobs_pilot")

    async with open_database(settings.mongo_db_name) as database:
        searches = SavedSearchRepository(database)
        notifications = NotificationRepository(database)
        digest_state = DigestStateRepository(database)
        digest_delivery = DigestDeliveryRepository(database)
        jobs = JobRepository(database)
        proc = AlertProcessor(searches=searches, notifications=notifications, settings=settings)

        sub_a = str(uuid.uuid4())
        sub_b = str(uuid.uuid4())
        for sid in (sub_a, sub_b):
            await database.alert_subscribers.insert_one(
                {
                    "subscriber_id": sid,
                    "token_hash": f"uat-{sid}",
                    "purpose": TEST_SUBSCRIBER_TAG,
                    "created_at": datetime.now(UTC),
                }
            )

        await searches.create(
            subscriber_id=sub_a,
            payload={
                "q": "Software Engineer",
                "country_code": "PK",
                "alerts_enabled": True,
                "digest_enabled": True,
                "digest_timezone": "Asia/Karachi",
                "digest_local_time": "00:00",
                "digest_max_jobs": 10,
            },
        )
        await searches.create(
            subscriber_id=sub_a,
            payload={
                "q": "Engineer",
                "country_code": "PK",
                "alerts_enabled": True,
                "enabled": True,
            },
        )

        job = await _insert_synthetic_job(
            database, suffix="create", title="Software Engineer Backend", country="PK"
        )
        created = await proc.process_job_persisted(job, outcome=JobUpsertOutcome.CREATED)
        dup = await proc.process_job_persisted(job, outcome=JobUpsertOutcome.UNCHANGED)
        job["title"] = "Software Engineer Backend (Updated)"
        updated_n = await proc.process_job_persisted(job, outcome=JobUpsertOutcome.UPDATED)
        job["status"] = JobStatus.EXPIRED.value
        await proc.process_job_persisted(job, outcome=JobUpsertOutcome.UNCHANGED)
        job["status"] = JobStatus.ACTIVE.value
        reactivated_n = await proc.process_job_persisted(
            job, outcome=JobUpsertOutcome.UNCHANGED, reactivated=True
        )

        _, total_a, unread_a = await notifications.list_for_subscriber(
            subscriber_id=sub_a, page=1, page_size=50
        )
        _, total_b, _unread_b = await notifications.list_for_subscriber(
            subscriber_id=sub_b, page=1, page_size=50
        )

        digest_svc = DailyDigestService(
            searches=searches,
            notifications=notifications,
            digest_state=digest_state,
            digest_delivery=digest_delivery,
            jobs=jobs,
            settings=settings,
        )
        preview_1 = await digest_svc.run_for_subscriber(sub_a, preview=True)
        preview_2 = await digest_svc.run_for_subscriber(sub_a, preview=True)
        khi = ZoneInfo("Asia/Karachi")
        local_today = datetime.now(UTC).astimezone(khi).date()
        early_local = datetime(
            local_today.year,
            local_today.month,
            local_today.day,
            0,
            1,
            tzinfo=khi,
        )
        late_local = datetime(
            local_today.year,
            local_today.month,
            local_today.day,
            12,
            0,
            tzinfo=khi,
        )
        early = await digest_svc.run_for_subscriber(
            sub_a, preview=False, now=early_local.astimezone(UTC)
        )
        late = await digest_svc.run_for_subscriber(
            sub_a, preview=False, now=late_local.astimezone(UTC)
        )
        late_dup = await digest_svc.run_for_subscriber(
            sub_a,
            preview=False,
            now=late_local.replace(minute=30).astimezone(UTC),
        )

        return {
            "created_notifications": created,
            "unchanged_duplicate": dup,
            "updated_notifications": updated_n,
            "reactivated_notifications": reactivated_n,
            "subscriber_a_total": total_a,
            "subscriber_a_unread": unread_a,
            "subscriber_b_total": total_b,
            "preview_eligible": preview_1.get("eligible_count"),
            "preview_repeat_ok": preview_1 == preview_2,
            "digest_early_status": early.get("status"),
            "digest_late_status": late.get("status"),
            "digest_late_created": late.get("created"),
            "digest_idempotent": late_dup.get("status"),
        }


def main() -> None:
    logging.basicConfig(level=logging.INFO)
    parser = argparse.ArgumentParser()
    parser.add_argument("--run", action="store_true")
    _ = parser.parse_args()
    print(asyncio.run(run_uat()))


if __name__ == "__main__":
    main()
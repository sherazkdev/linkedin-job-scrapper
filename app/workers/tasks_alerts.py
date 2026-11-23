"""Alert tasks (callable; not scheduled — Beat remains off)."""

from __future__ import annotations

import asyncio
import logging

from app.core.config import get_settings
from app.database.temp_database import open_database
from app.modules.alerts.digest import DailyDigestService
from app.modules.alerts.processor import AlertProcessor
from app.modules.alerts.repositories import (
    DigestStateRepository,
    NotificationRepository,
    SavedSearchRepository,
)
from app.modules.jobs.repositories.job_repository import JobRepository
from app.workers.celery_app import celery_app

logger = logging.getLogger(__name__)


@celery_app.task(name="app.workers.tasks_alerts.match_job_document")
def match_job_document_task(job_id: str) -> dict:
    """Re-run matching for a single job (admin/testing; requires ALERTS_MATCHING_ENABLED)."""
    settings = get_settings()
    if not settings.alerts_matching_enabled:
        return {"status": "disabled"}

    async def _run() -> dict:
        async with open_database(settings.mongo_db_name) as database:
            jobs = JobRepository(database)
            from bson import ObjectId

            job = await jobs.get_by_id(job_id) if ObjectId.is_valid(job_id) else None
            if job is None:
                return {"status": "not_found"}
            from app.modules.collection.models.enums import JobUpsertOutcome

            proc = AlertProcessor(
                searches=SavedSearchRepository(database),
                notifications=NotificationRepository(database),
                settings=settings,
            )
            n = await proc.process_job_persisted(
                job, outcome=JobUpsertOutcome.CREATED, reactivated=False
            )
            return {"status": "ok", "created": n}

    return asyncio.run(_run())


@celery_app.task(name="app.workers.tasks_alerts.run_daily_digest")
def run_daily_digest_task(subscriber_id: str) -> dict:
    settings = get_settings()
    if not settings.alerts_digest_enabled:
        return {"status": "disabled"}

    async def _run() -> dict:
        async with open_database(settings.mongo_db_name) as database:
            svc = DailyDigestService(
                searches=SavedSearchRepository(database),
                notifications=NotificationRepository(database),
                digest_state=DigestStateRepository(database),
                jobs=JobRepository(database),
                settings=settings,
            )
            return await svc.run_for_subscriber(subscriber_id)

    return asyncio.run(_run())


@celery_app.task(name="app.workers.tasks_alerts.inspect_alert_pipeline")
def inspect_alert_pipeline_task() -> dict:
    """Read-only counts for alert collections (ops/testing; no delivery)."""
    settings = get_settings()

    async def _run() -> dict:
        async with open_database(settings.mongo_db_name) as database:
            subs = await database["alert_subscribers"].count_documents({})
            searches = await database["saved_job_searches"].count_documents({})
            enabled = await database["saved_job_searches"].count_documents(
                {"enabled": True, "alerts_enabled": True}
            )
            notifs = await database["alert_notifications"].count_documents({})
            unread = await database["alert_notifications"].count_documents({"read_at": None})
            return {
                "status": "ok",
                "subscribers": subs,
                "saved_searches": searches,
                "alert_enabled_searches": enabled,
                "notifications": notifs,
                "unread_notifications": unread,
                "matching_enabled": settings.alerts_matching_enabled,
                "digest_enabled": settings.alerts_digest_enabled,
                "push_enabled": settings.alerts_push_enabled,
            }

    return asyncio.run(_run())
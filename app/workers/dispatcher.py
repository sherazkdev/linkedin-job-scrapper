"""Identify eligible MongoDB collection targets and enqueue worker tasks."""

import asyncio
import logging
from typing import Any

from app.core.config import Settings, get_settings
from app.database.temp_database import open_database
from app.modules.collection.repositories.target_repository import TargetRepository
from app.modules.collection.repositories.checkpoint_repository import (
    normalize_search_location_key,
)
from app.modules.jobs.models.job import JobSource
from app.workers.policy import allowed_task_sources

logger = logging.getLogger(__name__)


def _dispatch_allowed_sources(settings: Settings) -> list[JobSource]:
    allowed = list(allowed_task_sources(settings))
    raw = settings.celery_dispatch_source_allowlist
    if not raw or not raw.strip():
        return allowed
    allowlist = {
        part.strip().lower()
        for part in raw.split(",")
        if part.strip()
    }
    filtered = [source for source in allowed if source.value in allowlist]
    if filtered:
        logger.info("Dispatcher source allowlist active sources=%s", [s.value for s in filtered])
    return filtered


async def fetch_eligible_targets(
    settings: Settings, *, limit: int | None = None
) -> list[dict[str, Any]]:
    allowed = _dispatch_allowed_sources(settings)
    db_name = settings.celery_worker_mongo_db_name
    if (
        db_name == settings.mongo_db_name
        and not settings.allow_collection_production_db
        and not db_name.endswith("_test")
    ):
        db_name = f"{settings.mongo_db_name}_test"
    async with open_database(db_name) as database:
        repo = TargetRepository(database)
        await repo.ensure_defaults()
        dispatch_cap = limit if limit is not None else max(settings.celery_dispatch_max_per_tick, 1)
        return await repo.list_eligible_targets(allowed_sources=allowed, limit=dispatch_cap)


def target_max_jobs(doc: dict[str, Any], settings: Settings) -> int:
    configured = doc.get("max_jobs_per_run")
    if isinstance(configured, int) and configured > 0:
        return min(configured, 500)
    return settings.celery_collection_max_jobs_default


def dispatch_eligible_sync() -> dict[str, Any]:
    """Sync dispatcher: fetch targets in one event loop, enqueue tasks outside it."""
    settings = get_settings()
    targets = asyncio.run(fetch_eligible_targets(settings))
    queued: list[str] = []
    skipped_linkedin = 0

    from app.workers.tasks import run_collection_task

    max_per_tick = settings.celery_dispatch_max_per_tick
    for doc in targets:
        if len(queued) >= max_per_tick:
            break
        source = JobSource(doc["source"])
        if source == JobSource.LINKEDIN and not settings.celery_allow_linkedin_tasks:
            skipped_linkedin += 1
            continue
        loc_key = normalize_search_location_key(doc.get("search_location"))
        loc_suffix = f":{loc_key}" if loc_key else ""
        key = f"{doc['source']}:{doc['country_code']}:{doc['keyword']}{loc_suffix}"
        max_jobs = target_max_jobs(doc, settings)
        slug_kw = str(doc["keyword"]).strip().lower().replace(" ", "_")
        slug_loc = loc_key.replace(",", "").replace(" ", "_")[:48] if loc_key else ""
        task_id = f"collect-{doc['source']}-{doc['country_code']}-{slug_kw}"
        if slug_loc:
            task_id = f"{task_id}-{slug_loc}"
        search_location = doc.get("search_location") or None
        if isinstance(search_location, str) and not search_location.strip():
            search_location = None
        try:
            run_collection_task.apply_async(
                kwargs={
                    "source": doc["source"],
                    "country_code": doc["country_code"],
                    "keyword": doc["keyword"],
                    "max_jobs": max_jobs,
                    "search_location": search_location,
                },
                queue=settings.celery_task_default_queue,
                task_id=task_id,
            )
        except Exception:
            logger.info("Skip dispatch; task may already be active task_id=%s", task_id)
            continue
        queued.append(key)
        logger.info(
            "Dispatched collection task source=%s country=%s keyword=%s max_jobs=%s",
            doc["source"],
            doc["country_code"],
            doc["keyword"],
            max_jobs,
        )
    return {
        "eligible_count": len(targets),
        "queued_count": len(queued),
        "queued_keys": queued,
        "skipped_linkedin": skipped_linkedin,
    }

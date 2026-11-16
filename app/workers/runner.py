"""Run async collection pipeline from sync Celery workers (fresh event loop + Mongo client)."""

import asyncio
import logging
from typing import Any

from app.core.config import Settings, get_settings
from app.database.temp_database import open_database
from app.modules.collection.factory import build_collector
from app.modules.collection.linkedin.errors import LinkedInCollectionError
from app.modules.collection.repositories.target_repository import TargetRepository
from app.modules.collection.services.collector import CollectionLockError
from app.modules.jobs.models.job import JobDataProvenance, JobSource
from app.workers.policy import assert_source_allowed

logger = logging.getLogger(__name__)


def _resolve_worker_db_name(settings: Settings) -> str:
    db_name = settings.celery_worker_mongo_db_name
    if (
        db_name == settings.mongo_db_name
        and not settings.allow_collection_production_db
        and not db_name.endswith("_test")
    ):
        raise RuntimeError(
            f"Worker MongoDB '{db_name}' is production; set CELERY_WORKER_MONGO_DB_NAME "
            "to an isolated database (e.g. global_jobs_test) or set "
            "ALLOW_COLLECTION_PRODUCTION_DB=true."
        )
    return db_name


async def _collect_async(
    *,
    source: JobSource,
    country_code: str,
    keyword: str,
    max_jobs: int,
    run_owner: str,
    settings: Settings,
    db_name: str,
    search_location: str | None = None,
) -> dict[str, Any]:
    assert_source_allowed(settings, source)
    if source == JobSource.LINKEDIN:
        if settings.allow_live_linkedin_collection:
            provenance = JobDataProvenance.LIVE_API_VERIFIED
        elif settings.linkedin_offline_html_root:
            provenance = JobDataProvenance.OFFLINE_PROVIDER_FIXTURE
        else:
            provenance = JobDataProvenance.UNKNOWN
    else:
        provenance = JobDataProvenance.SYNTHETIC_FIXTURE
    async with open_database(db_name) as database:
        target_repo = TargetRepository(database)
        if source == JobSource.FIXTURE:
            await target_repo.ensure_defaults()
        else:
            await target_repo.upsert_target(
                source=source,
                country_code=country_code,
                keyword=keyword,
                search_location=search_location,
            )
        collector = build_collector(
            database,
            settings,
            source,
            target_cooldown_seconds=settings.celery_target_cooldown_seconds,
            linkedin_access_pause_seconds=settings.celery_linkedin_access_pause_seconds,
        )
        try:
            return await collector.collect(
                source=source,
                country_code=country_code,
                keyword=keyword,
                max_jobs=max_jobs,
                dry_run=False,
                run_owner=run_owner,
                data_provenance=provenance,
                search_location=search_location,
            )
        finally:
            await collector.shutdown()


def run_collection_sync(
    *,
    source: str,
    country_code: str,
    keyword: str,
    max_jobs: int,
    run_owner: str,
    search_location: str | None = None,
) -> dict[str, Any]:
    settings = get_settings()
    job_source = JobSource(source)
    db_name = _resolve_worker_db_name(settings)
    try:
        return asyncio.run(
            _collect_async(
                source=job_source,
                country_code=country_code,
                keyword=keyword,
                max_jobs=max_jobs,
                run_owner=run_owner,
                settings=settings,
                db_name=db_name,
                search_location=search_location,
            )
        )
    except LinkedInCollectionError:
        raise
    except CollectionLockError:
        raise


def renew_target_lease_sync(*, target_id: str, owner: str, lease_seconds: int) -> bool:
    settings = get_settings()
    db_name = _resolve_worker_db_name(settings)

    async def _renew() -> bool:
        from bson import ObjectId

        async with open_database(db_name) as database:
            repo = TargetRepository(database)
            return await repo.renew_lock(
                ObjectId(target_id),
                owner=owner,
                lease_seconds=lease_seconds,
            )

    return asyncio.run(_renew())

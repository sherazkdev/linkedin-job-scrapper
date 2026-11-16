"""Celery tasks for scheduled and on-demand fixture collection."""

import logging
import random

from celery import Task

from app.core.config import get_settings
from app.modules.collection.linkedin.errors import LinkedInCollectionError
from app.modules.collection.services.collector import CollectionLockError
from app.workers.celery_app import celery_app
from app.workers.dispatcher import dispatch_eligible_sync
from app.workers.retries import is_transient_worker_failure
from app.workers.runner import run_collection_sync

logger = logging.getLogger(__name__)


class CollectionTask(Task):
    autoretry_for: tuple[type[BaseException], ...] = ()
    retry_backoff = True
    retry_backoff_max = 300
    retry_jitter = True

    def on_failure(
        self,
        exc: BaseException,
        task_id: str,
        args: tuple,
        kwargs: dict,
        einfo: object,
    ) -> None:
        logger.error(
            "Collection task failed task_id=%s type=%s transient=%s",
            task_id,
            exc.__class__.__name__,
            is_transient_worker_failure(exc),
        )


@celery_app.task(
    bind=True,
    base=CollectionTask,
    name="app.workers.tasks.run_collection_task",
)
def run_collection_task(
    self: CollectionTask,
    *,
    source: str,
    country_code: str,
    keyword: str,
    max_jobs: int,
    search_location: str | None = None,
) -> dict:
    settings = get_settings()
    run_owner = f"celery:{self.request.id}"
    logger.info(
        "Worker collection start source=%s country=%s keyword=%s max_jobs=%s owner=%s",
        source,
        country_code,
        keyword,
        max_jobs,
        run_owner,
    )
    try:
        summary = run_collection_sync(
            source=source,
            country_code=country_code,
            keyword=keyword,
            max_jobs=max_jobs,
            run_owner=run_owner,
            search_location=search_location,
        )
        logger.info(
            "Worker collection finished run_id=%s stats=%s",
            summary.get("run_id"),
            summary.get("stats"),
        )
        return summary
    except CollectionLockError as exc:
        logger.warning(
            "Collection lock busy country=%s keyword=%s location=%s — no Celery retry",
            country_code,
            keyword,
            search_location,
        )
        raise
    except LinkedInCollectionError as exc:
        logger.error(
            "LinkedIn collection failed state=%s retryable=%s",
            exc.state.value,
            exc.retryable,
        )
        raise RuntimeError(f"linkedin:{exc.state.value}") from exc
    except Exception as exc:
        transient = is_transient_worker_failure(exc)
        under_limit = self.request.retries < settings.celery_task_max_retries
        if transient and under_limit:
            countdown = min(60 * (2**self.request.retries), 300) + random.randint(0, 20)
            raise self.retry(exc=exc, countdown=countdown) from exc
        raise


@celery_app.task(name="app.workers.tasks.dispatch_collection_targets")
def dispatch_collection_targets() -> dict:
    settings = get_settings()
    from app.workers.policy import linkedin_scheduling_enabled

    if linkedin_scheduling_enabled(settings):
        logger.info(
            "LinkedIn scheduling enabled live=%s offline_root=%s",
            settings.allow_live_linkedin_collection,
            bool(settings.linkedin_offline_html_root),
        )
    else:
        logger.debug("Dispatcher restricted to fixture sources (LinkedIn scheduling off)")
    return dispatch_eligible_sync()

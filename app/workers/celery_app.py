"""Celery application (Redis broker, collection queue)."""

from celery import Celery
from celery.signals import worker_process_init, worker_process_shutdown
from kombu import Queue

from app.core.config import get_settings
from app.core.logging import configure_logging
from app.workers.redis_urls import resolve_celery_broker_url, resolve_celery_result_backend

settings = get_settings()
configure_logging(settings)

broker_url = resolve_celery_broker_url(settings.redis_url, settings.celery_broker_url)
result_backend = resolve_celery_result_backend(settings.redis_url, settings.celery_result_backend)

celery_app = Celery("global_jobs", include=["app.workers.tasks"])
celery_app.conf.update(
    broker_url=broker_url,
    result_backend=result_backend,
    task_default_queue=settings.celery_task_default_queue,
    task_queues=(Queue(settings.celery_task_default_queue),),
    task_track_started=True,
    task_acks_late=True,
    worker_prefetch_multiplier=1,
    worker_hijack_root_logger=False,
    broker_connection_retry_on_startup=True,
    task_time_limit=settings.celery_task_time_limit,
    task_soft_time_limit=settings.celery_task_soft_time_limit,
    result_expires=86400,
    task_annotations={
        "app.workers.tasks.run_collection_task": {
            "max_retries": settings.celery_task_max_retries,
        },
    },
    beat_schedule={
        "dispatch-collection-targets": {
            "task": "app.workers.tasks.dispatch_collection_targets",
            "schedule": float(settings.celery_beat_dispatch_interval_seconds),
        },
    },
)


@worker_process_init.connect
def _worker_process_init(**_: object) -> None:
    configure_logging(get_settings())


@worker_process_shutdown.connect
def _worker_process_shutdown(**_: object) -> None:
    pass

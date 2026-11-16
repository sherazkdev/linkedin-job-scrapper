import os

from app.core.config import get_settings
from app.modules.jobs.models.job import JobSource
from app.workers.policy import allowed_task_sources, linkedin_scheduling_enabled


def test_linkedin_scheduler_requires_explicit_flag() -> None:
    os.environ.pop("CELERY_ALLOW_LINKEDIN_TASKS", None)
    os.environ.pop("ALLOW_LIVE_LINKEDIN_COLLECTION", None)
    os.environ.pop("LINKEDIN_OFFLINE_HTML_ROOT", None)
    get_settings.cache_clear()
    settings = get_settings()
    assert JobSource.LINKEDIN not in allowed_task_sources(settings)
    assert not linkedin_scheduling_enabled(settings)


def test_linkedin_scheduler_live_opt_in() -> None:
    os.environ["CELERY_ALLOW_LINKEDIN_TASKS"] = "true"
    os.environ["ALLOW_LIVE_LINKEDIN_COLLECTION"] = "true"
    get_settings.cache_clear()
    settings = get_settings()
    assert JobSource.LINKEDIN in allowed_task_sources(settings)


def test_linkedin_scheduler_offline_fixtures() -> None:
    os.environ["CELERY_ALLOW_LINKEDIN_TASKS"] = "true"
    os.environ["ALLOW_LIVE_LINKEDIN_COLLECTION"] = "false"
    os.environ["LINKEDIN_OFFLINE_HTML_ROOT"] = "/fixtures/linkedin"
    get_settings.cache_clear()
    settings = get_settings()
    assert linkedin_scheduling_enabled(settings)
    assert JobSource.LINKEDIN in allowed_task_sources(settings)
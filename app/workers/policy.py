from app.core.config import Settings
from app.modules.jobs.models.job import JobSource


def linkedin_scheduling_enabled(settings: Settings) -> bool:
    if not settings.celery_allow_linkedin_tasks:
        return False
    if settings.allow_live_linkedin_collection:
        return True
    return bool(settings.linkedin_offline_html_root)


def allowed_task_sources(settings: Settings) -> frozenset[JobSource]:
    """Sources Celery may queue.

    Public boards and market-search (Adzuna) are CLI-only — never scheduled.
    LinkedIn excluded unless explicitly allowed (live or offline HTML fixtures).
    """
    allowed = {JobSource.FIXTURE}
    if linkedin_scheduling_enabled(settings):
        allowed.add(JobSource.LINKEDIN)
    return frozenset(allowed)


def assert_source_allowed(settings: Settings, source: JobSource) -> None:
    if source not in allowed_task_sources(settings):
        raise ValueError(
            f"Source '{source.value}' is not allowed for scheduled/worker collection "
            f"(CELERY_ALLOW_LINKEDIN_TASKS={settings.celery_allow_linkedin_tasks})."
        )

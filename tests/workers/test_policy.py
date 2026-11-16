from app.core.config import Settings
from app.modules.jobs.models.job import JobSource
from app.workers.policy import allowed_task_sources, assert_source_allowed


def _settings(**overrides: object) -> Settings:
    base = {"mongo_uri": "mongodb://localhost", "redis_url": "redis://localhost"}
    base.update(overrides)
    return Settings(**base)


def test_fixture_allowed_by_default() -> None:
    settings = _settings(
        celery_allow_linkedin_tasks=False,
        allow_live_linkedin_collection=False,
    )
    allowed = allowed_task_sources(settings)
    assert JobSource.FIXTURE in allowed
    assert JobSource.LINKEDIN not in allowed
    for board in (JobSource.GREENHOUSE, JobSource.LEVER, JobSource.ASHBY):
        assert board not in allowed


def test_linkedin_requires_dual_flags() -> None:
    settings = _settings(
        celery_allow_linkedin_tasks=True,
        allow_live_linkedin_collection=False,
    )
    assert JobSource.LINKEDIN not in allowed_task_sources(settings)


def test_assert_source_blocks_linkedin() -> None:
    settings = _settings()
    try:
        assert_source_allowed(settings, JobSource.LINKEDIN)
        raise AssertionError("expected ValueError")
    except ValueError as exc:
        assert "not allowed" in str(exc)

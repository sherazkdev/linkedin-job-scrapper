from app.modules.coverage.sources import SOURCE_CAPABILITIES, CollectionMode
from app.modules.jobs.models.job import JobSource


def test_employer_boards_not_global_search() -> None:
    for source in (JobSource.GREENHOUSE, JobSource.LEVER, JobSource.ASHBY):
        meta = SOURCE_CAPABILITIES[source]
        assert meta["global_country_keyword_search"] is False
        assert meta["mode"] == CollectionMode.EMPLOYER_BOARD


def test_linkedin_not_celery_scheduled_by_default() -> None:
    meta = SOURCE_CAPABILITIES[JobSource.LINKEDIN]
    assert meta["celery_scheduled"] is False
    assert meta["verified_live_data"] is False


def test_fixture_simulates_markets_only() -> None:
    meta = SOURCE_CAPABILITIES[JobSource.FIXTURE]
    assert meta["verified_live_data"] is False
    assert meta["celery_scheduled"] is True
from datetime import UTC, datetime, timedelta

from app.modules.alerts.matcher import job_matches_saved_search
from app.modules.jobs.models.job import EmploymentType, JobStatus


def _job(**overrides):
    base = {
        "status": JobStatus.ACTIVE.value,
        "title": "Software Engineer",
        "company": "Acme",
        "country_code": "PK",
        "search_country_code": "PK",
        "city": "Islamabad",
        "employment_type": EmploymentType.FULL_TIME.value,
        "is_remote": False,
        "posted_at": datetime.now(UTC) - timedelta(hours=2),
        "first_seen_at": datetime.now(UTC) - timedelta(hours=2),
    }
    base.update(overrides)
    return base


def test_match_keyword_country_city() -> None:
    search = {
        "enabled": True,
        "alerts_enabled": True,
        "q": "software",
        "country_code": "PK",
        "city": "Islamabad",
    }
    assert job_matches_saved_search(_job(), search, max_age_days=7)


def test_city_mismatch() -> None:
    search = {"enabled": True, "alerts_enabled": True, "city": "Karachi", "country_code": "PK"}
    assert not job_matches_saved_search(_job(city="Islamabad"), search, max_age_days=7)


def test_expired_job_excluded() -> None:
    old = datetime.now(UTC) - timedelta(days=30)
    search = {"enabled": True, "alerts_enabled": True}
    assert not job_matches_saved_search(
        _job(posted_at=old, first_seen_at=old), search, max_age_days=7
    )


def test_disabled_search() -> None:
    search = {"enabled": False, "alerts_enabled": True}
    assert not job_matches_saved_search(_job(), search, max_age_days=7)
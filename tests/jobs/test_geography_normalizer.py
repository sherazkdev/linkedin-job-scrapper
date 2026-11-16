from datetime import UTC, datetime

from app.modules.collection.models.raw_job import RawJobRecord
from app.modules.collection.services.normalizer import JobNormalizer
from app.modules.jobs.models.job import JobSource


def test_normalizer_splits_search_and_actual_country() -> None:
    raw = RawJobRecord(
        source_job_id="geo-1",
        title="Engineer",
        company="Acme",
        search_country_code="US",
        location_text="Berlin, Germany",
        description="Fictional role",
        job_url="https://example.org/1",
        posted_at=datetime(2026, 1, 1, tzinfo=UTC),
    )
    job = JobNormalizer(JobSource.FIXTURE).normalize(raw)
    assert job.search_country_code == "US"
    assert job.country_code == "DE"
    assert job.location_text == "Berlin, Germany"


def test_normalizer_remote_without_country() -> None:
    raw = RawJobRecord(
        source_job_id="geo-2",
        title="Engineer",
        company="Acme",
        search_country_code="DE",
        location_text="Remote",
        workplace_type="remote",
        description="Fictional role",
        job_url="https://example.org/2",
        posted_at=datetime(2026, 1, 1, tzinfo=UTC),
    )
    job = JobNormalizer(JobSource.FIXTURE).normalize(raw)
    assert job.country_code is None
    assert job.is_remote is True
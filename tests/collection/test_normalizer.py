from datetime import UTC, datetime

import pytest

from app.modules.collection.models.raw_job import RawJobRecord
from app.modules.collection.services.normalizer import JobNormalizationError, JobNormalizer
from app.modules.jobs.models.job import JobSource


def test_normalizer_accepts_valid_record() -> None:
    raw = RawJobRecord(
        source_job_id=" fx-001 ",
        title="  Backend Engineer  ",
        company="Northwind Collective",
        search_country_code="de",
        location_text="Berlin, Germany",
        city="Berlin",
        description="Fictional listing",
        job_url="https://example.org/jobs/fx-001",
        employment_type="full_time",
        workplace_type="remote",
        posted_at=datetime(2025, 1, 1, tzinfo=UTC),
    )
    job = JobNormalizer(JobSource.FIXTURE).normalize(raw)
    assert job.search_country_code == "DE"
    assert job.country_code == "DE"
    assert job.title == "Backend Engineer"


def test_normalizer_allows_missing_posted_at_and_empty_description() -> None:
    raw = RawJobRecord(
        source_job_id="fx-003",
        title="Analyst",
        company="Northwind",
        search_country_code="US",
        location_text="Remote",
        description="",
        description_provided=False,
        job_url="https://example.org/jobs/fx-003",
        posted_at=None,
    )
    job = JobNormalizer(JobSource.FIXTURE).normalize(raw)
    assert job.posted_at is None
    assert job.description == ""
    assert job.description_provided is False


@pytest.mark.parametrize(
    "field,value",
    [
        ("job_url", "not-a-url"),
        ("search_country_code", "GER"),
        ("title", "   "),
    ],
)
def test_normalizer_rejects_invalid(field: str, value) -> None:
    data = {
        "source_job_id": "fx-002",
        "title": "Role",
        "company": "Acme",
        "search_country_code": "US",
        "location_text": "Austin, United States",
        "description": "Valid",
        "job_url": "https://example.org/x",
        "posted_at": datetime.now(UTC),
    }
    data[field] = value
    raw = RawJobRecord(**data)
    with pytest.raises(JobNormalizationError):
        JobNormalizer(JobSource.FIXTURE).normalize(raw)

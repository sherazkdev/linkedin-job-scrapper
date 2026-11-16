import json
from pathlib import Path

from app.modules.collection.boards.parsers import (
    ashby_jobs_to_raw,
    greenhouse_jobs_to_raw,
    lever_postings_to_raw,
)
from app.modules.collection.services.normalizer import JobNormalizer
from app.modules.jobs.models.job import JobSource

FIXTURE_ROOT = Path(__file__).resolve().parents[1] / "fixtures" / "public_boards"


def test_greenhouse_parser_matches_keyword() -> None:
    payload = json.loads((FIXTURE_ROOT / "greenhouse" / "sample.json").read_text(encoding="utf-8"))
    jobs, metrics = greenhouse_jobs_to_raw(
        payload["jobs_payload"],
        board_site="sample",
        company_name=payload["company_name"],
        search_country_code="US",
        keyword="engineer",
        skip_ids=set(),
        limit=5,
    )
    assert metrics["valid_listings"] == 1
    assert jobs[0].source_job_id == "sample:4011001"
    assert "greenhouse.io" in jobs[0].job_url


def test_lever_parser_requires_posted_timestamp_handling() -> None:
    payload = json.loads((FIXTURE_ROOT / "lever" / "sample.json").read_text(encoding="utf-8"))
    jobs, _ = lever_postings_to_raw(
        payload["postings"],
        board_site="sample",
        company_name="Lever Sample",
        search_country_code="SE",
        keyword="*",
        skip_ids=set(),
        limit=5,
    )
    assert jobs[0].posted_at is not None


def test_ashby_parser_and_normalizer_geography() -> None:
    payload = json.loads((FIXTURE_ROOT / "ashby" / "sample.json").read_text(encoding="utf-8"))
    jobs, _ = ashby_jobs_to_raw(
        payload["board_payload"],
        board_site="sample",
        company_name="Ashby Sample",
        search_country_code="GB",
        keyword="*",
        skip_ids=set(),
        limit=5,
    )
    normalizer = JobNormalizer(JobSource.ASHBY)
    job = normalizer.normalize(jobs[0])
    assert job.search_country_code == "GB"
    assert job.country_code == "GB"
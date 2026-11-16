from datetime import UTC, datetime

from app.modules.collection.boards.parsers import greenhouse_jobs_to_raw


def test_greenhouse_uses_first_published_only() -> None:
    payload = {
        "jobs": [
            {
                "id": 99,
                "title": "SRE",
                "absolute_url": "https://boards.greenhouse.io/acme/jobs/99",
                "first_published": "2024-06-01T10:00:00Z",
                "updated_at": "2025-01-01T10:00:00Z",
                "content": "<p>Operate systems</p>",
            }
        ]
    }
    jobs, _ = greenhouse_jobs_to_raw(
        payload,
        board_site="acme",
        company_name="Acme",
        search_country_code="US",
        keyword="*",
        skip_ids=set(),
        limit=5,
    )
    assert jobs[0].posted_at == datetime(2024, 6, 1, 10, 0, tzinfo=UTC)
    assert jobs[0].source_updated_at == datetime(2025, 1, 1, 10, 0, tzinfo=UTC)


def test_greenhouse_never_maps_updated_at_to_posted_at() -> None:
    payload = {
        "jobs": [
            {
                "id": 100,
                "title": "Analyst",
                "absolute_url": "https://boards.greenhouse.io/acme/jobs/100",
                "updated_at": "2025-01-01T10:00:00Z",
                "content": "<p>Analysis</p>",
            }
        ]
    }
    jobs, metrics = greenhouse_jobs_to_raw(
        payload,
        board_site="acme",
        company_name="Acme",
        search_country_code="US",
        keyword="*",
        skip_ids=set(),
        limit=5,
    )
    assert jobs[0].posted_at is None
    assert jobs[0].source_updated_at is not None
    assert metrics["missing_posted_at"] == 1
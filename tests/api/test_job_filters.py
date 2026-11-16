from app.modules.jobs.models.job import JobStatus
from app.modules.jobs.schemas.filters import JobListFilters, build_mongo_query


def test_country_code_does_not_include_search_country() -> None:
    q = build_mongo_query(JobListFilters(country_code="DE", status=JobStatus.ACTIVE))
    assert q == {"$and": [{"status": "active"}, {"country_code": "DE"}]} or q == {
        "status": "active",
        "country_code": "DE",
    }
    assert "search_country_code" not in str(q)


def test_search_and_actual_country_separate() -> None:
    filters = JobListFilters(
        country_code="DE",
        search_country_code="US",
        status=JobStatus.ACTIVE,
    )
    q = build_mongo_query(filters)
    assert q == {
        "$and": [
            {"status": "active"},
            {"country_code": "DE"},
            {"search_country_code": "US"},
        ]
    }
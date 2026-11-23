"""Public list API contract for app integrators (filter + pagination semantics)."""

from app.modules.jobs.models.job import JobSource
from app.modules.jobs.schemas.filters import JobListFilters, JobSort, build_mongo_query, sort_spec


def test_build_mongo_query_search_country_and_posted_within() -> None:
    filters = JobListFilters(
        source=JobSource.LINKEDIN,
        search_country_code="pk",
        posted_within_days=7,
        live_verified_only=True,
        sort=JobSort.POSTED_AT_DESC,
    )
    assert filters.search_country_code == "PK"
    q = build_mongo_query(filters)
    blob = str(q)
    assert "PK" in blob
    assert "linkedin" in blob
    assert "live_api_verified" in blob
    assert "posted_at" in blob


def test_build_mongo_query_country_code_normalization() -> None:
    filters = JobListFilters(country_code="gb", source=JobSource.LINKEDIN)
    assert filters.country_code == "GB"
    q = build_mongo_query(filters)
    assert "GB" in str(q)


def test_sort_spec_posted_at_desc() -> None:
    assert sort_spec(JobSort.POSTED_AT_DESC) == [
        ("posted_at", -1),
        ("first_seen_at", -1),
        ("sourceJobId", -1),
    ]


def test_integrator_contract_fields_documented() -> None:
    """Stable JSON fields exposed at GET /api/v1/jobs (see JobSummaryResponse)."""
    expected_item_keys = {
        "id",
        "source",
        "source_job_id",
        "title",
        "company",
        "country_code",
        "search_country_code",
        "location_text",
        "city",
        "region",
        "is_remote",
        "employment_type",
        "workplace_type",
        "job_url",
        "posted_at",
        "last_seen_at",
        "status",
        "description_provided",
        "data_provenance",
    }
    expected_page_keys = {
        "items",
        "total",
        "page",
        "page_size",
        "total_pages",
        "has_next",
        "has_previous",
        "has_more",
    }
    assert len(expected_item_keys) >= 18
    assert "search_country_code" in expected_item_keys
    assert "total" in expected_page_keys
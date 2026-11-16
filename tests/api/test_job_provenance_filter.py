from app.modules.jobs.models.job import JobDataProvenance
from app.modules.jobs.schemas.filters import JobListFilters, build_mongo_query


def _provenance_in_query(query: dict, value: str) -> bool:
    if query.get("data_provenance") == value:
        return True
    clauses = query.get("$and")
    if isinstance(clauses, list):
        return any(c.get("data_provenance") == value for c in clauses if isinstance(c, dict))
    return False


def test_live_verified_only_filter() -> None:
    q = build_mongo_query(JobListFilters(live_verified_only=True))
    assert _provenance_in_query(q, JobDataProvenance.LIVE_API_VERIFIED.value)


def test_data_provenance_explicit_filter() -> None:
    q = build_mongo_query(
        JobListFilters(data_provenance=JobDataProvenance.OFFLINE_PROVIDER_FIXTURE)
    )
    assert _provenance_in_query(q, JobDataProvenance.OFFLINE_PROVIDER_FIXTURE.value)
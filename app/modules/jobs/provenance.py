"""Classify stored jobs by data origin (not by source enum alone)."""

from typing import Any

from app.modules.jobs.models.job import JobDataProvenance, JobSource

BOARD_SOURCES = frozenset(
    {JobSource.GREENHOUSE.value, JobSource.LEVER.value, JobSource.ASHBY.value}
)
MARKET_SEARCH_SOURCES = frozenset({JobSource.ADZUNA.value})
OFFLINE_SAMPLE_MARKERS = ("sample:", "sample/")


def resolve_collection_provenance(
    source: JobSource,
    *,
    used_offline_fixture: bool,
    live_network_used: bool,
) -> JobDataProvenance:
    if source == JobSource.FIXTURE:
        return JobDataProvenance.SYNTHETIC_FIXTURE
    if source == JobSource.DEMO:
        return JobDataProvenance.DEMO_SEED
    if used_offline_fixture or not live_network_used:
        return JobDataProvenance.OFFLINE_PROVIDER_FIXTURE
    return JobDataProvenance.LIVE_API_VERIFIED


def infer_provenance_from_job_document(doc: dict[str, Any]) -> JobDataProvenance:
    existing = doc.get("data_provenance")
    if isinstance(existing, str):
        try:
            provenance = JobDataProvenance(existing)
            if provenance != JobDataProvenance.UNKNOWN:
                return provenance
        except ValueError:
            pass

    source = str(doc.get("source", ""))
    if source == JobSource.DEMO.value:
        return JobDataProvenance.DEMO_SEED
    if source == JobSource.FIXTURE.value:
        return JobDataProvenance.SYNTHETIC_FIXTURE

    source_job_id = str(doc.get("sourceJobId") or doc.get("source_job_id") or "")
    lower_id = source_job_id.lower()

    provider_sources = BOARD_SOURCES | MARKET_SEARCH_SOURCES | {JobSource.LINKEDIN.value}
    if source in provider_sources:
        if any(lower_id.startswith(marker) for marker in OFFLINE_SAMPLE_MARKERS):
            return JobDataProvenance.OFFLINE_PROVIDER_FIXTURE
        if source == JobSource.LINKEDIN.value and "fixture" in lower_id:
            return JobDataProvenance.OFFLINE_PROVIDER_FIXTURE
        return JobDataProvenance.UNKNOWN

    return JobDataProvenance.UNKNOWN


def is_live_verified_job(doc: dict[str, Any]) -> bool:
    return doc.get("data_provenance") == JobDataProvenance.LIVE_API_VERIFIED.value
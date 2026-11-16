from app.modules.jobs.models.job import JobDataProvenance, JobSource
from app.modules.jobs.provenance import (
    infer_provenance_from_job_document,
    is_live_verified_job,
    resolve_collection_provenance,
)


def test_resolve_fixture_and_demo() -> None:
    assert (
        resolve_collection_provenance(
            JobSource.FIXTURE, used_offline_fixture=False, live_network_used=False
        )
        == JobDataProvenance.SYNTHETIC_FIXTURE
    )
    assert (
        resolve_collection_provenance(
            JobSource.DEMO, used_offline_fixture=False, live_network_used=False
        )
        == JobDataProvenance.DEMO_SEED
    )


def test_infer_offline_greenhouse_sample() -> None:
    doc = {"source": "greenhouse", "sourceJobId": "sample:4011001"}
    assert infer_provenance_from_job_document(doc) == JobDataProvenance.OFFLINE_PROVIDER_FIXTURE
    assert not is_live_verified_job(doc)


def test_grafanalabs_prefix_not_auto_live() -> None:
    doc = {"source": "greenhouse", "sourceJobId": "grafanalabs:12345"}
    assert infer_provenance_from_job_document(doc) == JobDataProvenance.UNKNOWN
    assert not is_live_verified_job(doc)


def test_explicit_live_provenance_only() -> None:
    doc = {
        "source": "greenhouse",
        "sourceJobId": "grafanalabs:12345",
        "data_provenance": "live_api_verified",
    }
    assert is_live_verified_job(doc)
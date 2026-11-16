from datetime import UTC, datetime
from typing import Any

from pymongo.asynchronous.database import AsyncDatabase

from app.core.config import get_settings
from app.database.collection_indexes import COLLECTION_TARGETS
from app.database.indexes import JOBS_COLLECTION
from app.modules.coverage.audit import audit_manifest_against_scheduler
from app.modules.coverage.manifest import default_manifest_path, load_manifest, validate_manifest
from app.modules.coverage.market_providers import build_country_capability_matrix, matrix_summary
from app.modules.coverage.repository import CoverageTargetRepository
from app.modules.coverage.sources import SOURCE_CAPABILITIES, CollectionMode, capability_matrix
from app.modules.jobs.models.job import JobDataProvenance, JobSource
from app.modules.jobs.provenance import infer_provenance_from_job_document, is_live_verified_job
from app.workers.policy import allowed_task_sources


async def _job_counts_by_provenance(database: AsyncDatabase[Any]) -> dict[str, Any]:
    jobs = database[JOBS_COLLECTION]
    by_stored: dict[str, int] = {}
    by_inferred: dict[str, int] = {}
    live_verified_by_country: dict[str, int] = {}
    live_verified_total = 0
    async for doc in jobs.find({}):
        stored = doc.get("data_provenance")
        if isinstance(stored, str):
            by_stored[stored] = by_stored.get(stored, 0) + 1
        inferred = infer_provenance_from_job_document(doc)
        by_inferred[inferred.value] = by_inferred.get(inferred.value, 0) + 1
        if is_live_verified_job(doc):
            live_verified_total += 1
            cc = doc.get("country_code") or "unknown"
            live_verified_by_country[str(cc)] = live_verified_by_country.get(str(cc), 0) + 1

    fixture_legacy = await jobs.count_documents(
        {
            "source": JobSource.FIXTURE.value,
            "data_provenance": {"$exists": False},
        }
    )
    return {
        "by_stored_provenance": by_stored,
        "by_inferred_provenance": by_inferred,
        "live_api_verified_total": live_verified_total,
        "live_api_verified_by_job_country": live_verified_by_country,
        "distinct_countries_live_verified": len(
            {k for k in live_verified_by_country if k != "unknown"}
        ),
        "legacy_missing_provenance_fixture_rows": fixture_legacy,
    }


async def build_coverage_report(database: AsyncDatabase[Any]) -> dict[str, Any]:
    settings = get_settings()
    now = datetime.now(UTC)

    manifest_meta: dict[str, Any] | None = None
    manifest_error: str | None = None
    try:
        data = load_manifest()
        manifest_meta = validate_manifest(data)
    except (OSError, ValueError) as exc:
        manifest_error = str(exc)

    repo = CoverageTargetRepository(database)
    configured = await repo.count_all()
    enabled_coverage = await repo.count_enabled()
    source_supported = await repo.count_source_supported()
    approved_active = await repo.count_approved_active()
    sched_compare = await repo.compare_with_collection_targets(database)
    scheduler_audit = await audit_manifest_against_scheduler(database)
    sched_enabled = await database[COLLECTION_TARGETS].count_documents({"enabled": True})

    job_provenance = await _job_counts_by_provenance(database)

    market_sources = [
        s.value
        for s, meta in SOURCE_CAPABILITIES.items()
        if meta.get("global_country_keyword_search") is True
        and s not in {JobSource.FIXTURE, JobSource.DEMO}
    ]
    board_sources = [
        s.value
        for s, meta in SOURCE_CAPABILITIES.items()
        if meta.get("mode") == CollectionMode.EMPLOYER_BOARD
    ]

    market_matrix_summary = matrix_summary()

    return {
        "generated_at": now.isoformat(),
        "manifest_path": str(default_manifest_path()),
        "manifest_validation": manifest_meta,
        "manifest_error": manifest_error,
        "required": {"countries": 40, "keywords": 50, "target_combinations": 2000},
        "target_layers": {
            "configured_manifest_combinations": 2000 if manifest_meta else None,
            "materialized_coverage_targets": configured,
            "source_supported_coverage_targets": source_supported,
            "enabled_coverage_targets": enabled_coverage,
            "approved_active_coverage_targets": approved_active,
            "scheduler_collection_targets_enabled": sched_enabled,
            "approved_runnable_combinations": approved_active,
        },
        "coverage_targets": {
            "configured_in_db": configured,
            "enabled_in_db": enabled_coverage,
            "disabled_by_default_policy": True,
        },
        "collection_targets_scheduler": sched_compare,
        "scheduler_vs_manifest_audit": scheduler_audit,
        "source_capability_matrix": capability_matrix(),
        "market_search_country_matrix_summary": market_matrix_summary,
        "authorization_gates": {
            "allow_live_linkedin_collection": settings.allow_live_linkedin_collection,
            "allow_live_public_board_collection": settings.allow_live_public_board_collection,
            "celery_allowed_sources": [s.value for s in allowed_task_sources(settings)],
        },
        "job_store_provenance": job_provenance,
        "non_real_job_counts": {
            "synthetic_fixture": job_provenance["by_inferred_provenance"].get(
                JobDataProvenance.SYNTHETIC_FIXTURE.value, 0
            ),
            "demo_seed": job_provenance["by_inferred_provenance"].get(
                JobDataProvenance.DEMO_SEED.value, 0
            ),
            "offline_provider_fixture": job_provenance["by_inferred_provenance"].get(
                JobDataProvenance.OFFLINE_PROVIDER_FIXTURE.value, 0
            ),
            "unknown": job_provenance["by_inferred_provenance"].get(
                JobDataProvenance.UNKNOWN.value, 0
            ),
        },
        "coverage_interpretation": {
            "target_configuration_equals_job_availability": False,
            "employer_boards_do_not_provide_global_search": board_sources,
            "potential_market_search_sources_pending_authorization": market_sources,
            "unmaterialized_coverage_targets_in_db": max(0, 2000 - configured)
            if manifest_meta
            else None,
        },
        "scheduler_scalability_notes": [
            "Beat dispatches eligible collection_targets only (fixture by default).",
            "2000 coverage rows are metadata; do not enqueue all without per-source budgets.",
            "Use cooldowns, concurrency limits, and provider-specific queues before scale-out.",
            "Materialize collection_targets from coverage only via explicit operator workflows.",
        ],
        "verdict": {
            "target_configuration_verified": manifest_meta is not None
            and manifest_meta.get("countries") == 40
            and manifest_meta.get("keywords") == 50
            and manifest_meta.get("targets") == 2000,
            "coverage_targets_materialized_in_db": configured == 2000,
            "market_search_source_feasibility_documented": market_matrix_summary[
                "countries_with_any_verified_provider"
            ]
            > 0,
            "real_global_data_coverage_verified": job_provenance["live_api_verified_total"] > 0
            and job_provenance["distinct_countries_live_verified"] >= 40,
            "disclaimer": (
                "JobSource label alone does not imply live data. "
                "Use data_provenance=live_api_verified for genuine API/board fetches."
            ),
        },
    }


def country_capability_matrix_for_ops() -> list[dict[str, Any]]:
    """Full 40-country matrix (for internal ops export / docs)."""
    return build_country_capability_matrix()
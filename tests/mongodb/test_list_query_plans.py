"""Explain plans for common job list queries (isolated test DB)."""

import pytest

from app.modules.jobs.models.job import JobStatus
from app.modules.jobs.schemas.filters import JobListFilters, JobSort, build_mongo_query, sort_spec


def _plan_uses_index(stage: dict) -> bool:
    if not stage:
        return False
    if stage.get("stage") == "IXSCAN":
        name = stage.get("indexName", "")
        return name.startswith("idx_")
    for key in ("inputStage", "outerStage", "thenStage", "elseStage"):
        child = stage.get(key)
        if isinstance(child, dict) and _plan_uses_index(child):
            return True
    return False


@pytest.mark.asyncio
async def test_country_list_uses_compound_index(
    require_integration: None,
    integration_db: None,
) -> None:
    from app.database.mongodb import get_mongodb

    db = get_mongodb().database
    query = build_mongo_query(
        JobListFilters(country_code="US", status=JobStatus.ACTIVE),
    )
    cursor = db["jobs"].find(query).sort(sort_spec(JobSort.POSTED_AT_DESC)).limit(20)
    explain = await cursor.explain()
    winning = explain.get("queryPlanner", {}).get("winningPlan", {})
    exec_stages = explain.get("executionStats", {}).get("executionStages", {})
    assert _plan_uses_index(winning) or _plan_uses_index(exec_stages), explain
    assert "COLLSCAN" not in str(explain).upper()
"""JobCollector persists LinkedIn page_index=0 after a run."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from app.modules.collection.adapters.base import AdapterFetchResult
from app.modules.collection.linkedin.checkpoint_policy import prepare_linkedin_run_checkpoint
from app.modules.collection.models.stats import CollectionStats
from app.modules.collection.services.collector import JobCollector
from app.modules.jobs.models.job import JobDataProvenance, JobSource


@pytest.mark.asyncio
async def test_fetch_and_process_linkedin_load_applies_fresh_page_policy() -> None:
    checkpoints = MagicMock()
    checkpoints.load = AsyncMock(
        return_value={"page_index": 8, "processed_ids": ["999"], "keyword": "se"}
    )
    checkpoints.save = AsyncMock()
    adapter = MagicMock()
    adapter.fetch_jobs = AsyncMock(
        return_value=AdapterFetchResult(
            jobs=[],
            checkpoint={"page_index": 3, "processed_ids": ["999"], "keyword": "se"},
            has_more=False,
            metrics={},
        )
    )
    collector = JobCollector(
        adapter=adapter,
        normalizer=MagicMock(),
        persistence=MagicMock(),
        run_service=MagicMock(),
        checkpoint_repository=checkpoints,
        target_repository=MagicMock(),
        error_handler=MagicMock(),
    )
    await collector._fetch_and_process(
        source=JobSource.LINKEDIN,
        country_code="PK",
        keyword="software engineer",
        max_jobs=5,
        persist=True,
        stats=CollectionStats(),
        data_provenance=JobDataProvenance.LIVE_API_VERIFIED,
        search_location=None,
        linkedin_ignore_checkpoint=False,
    )
    adapter.fetch_jobs.assert_awaited_once()
    _kwargs = adapter.fetch_jobs.await_args.kwargs
    assert _kwargs["checkpoint"]["page_index"] == 0
    checkpoints.save.assert_awaited_once()
    saved_ck = checkpoints.save.await_args.kwargs["checkpoint"]
    assert saved_ck["page_index"] == 0


@pytest.mark.asyncio
async def test_second_independent_run_still_page_zero() -> None:
    stored = {"page_index": 8, "processed_ids": ["1"]}
    first = prepare_linkedin_run_checkpoint(stored, ignore_stored=False)
    from app.modules.collection.linkedin.checkpoint_policy import persist_linkedin_run_checkpoint

    after_run = persist_linkedin_run_checkpoint({"page_index": 2, "processed_ids": ["1", "2"]})
    second = prepare_linkedin_run_checkpoint(after_run, ignore_stored=False)
    assert first is not None and second is not None
    assert first["page_index"] == 0
    assert second["page_index"] == 0
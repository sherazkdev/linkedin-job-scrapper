from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from app.modules.collection.models.enums import CollectionRunStatus
from app.modules.collection.models.run import CollectionRun
from app.modules.collection.models.stats import CollectionStats
from app.modules.collection.repositories.run_repository import RunRepository
from app.modules.jobs.models.job import JobSource


class CollectionRunService:
    def __init__(self, repository: RunRepository) -> None:
        self._repository = repository

    async def start(
        self,
        *,
        source: JobSource,
        country_code: str,
        keyword: str,
        dry_run: bool,
        search_location: str | None = None,
    ) -> CollectionRun:
        loc = (search_location or "").strip().lower()
        run = CollectionRun(
            run_id=str(uuid4()),
            source=source,
            country_code=country_code.upper(),
            keyword=keyword.strip().lower(),
            search_location=loc,
            status=CollectionRunStatus.RUNNING,
            started_at=datetime.now(UTC),
            dry_run=dry_run,
        )
        await self._repository.create_run(run)
        return run

    async def complete(
        self,
        run_id: str,
        *,
        status: CollectionRunStatus,
        stats: CollectionStats,
        error_summary: str | None = None,
    ) -> None:
        await self._repository.update_status(
            run_id,
            status=status,
            stats={
                "collected_count": stats.collected_count,
                "created_count": stats.created_count,
                "updated_count": stats.updated_count,
                "unchanged_count": stats.unchanged_count,
                "rejected_count": stats.rejected_count,
                "failed_count": stats.failed_count,
            },
            error_summary=error_summary,
        )

    async def get_running(
        self,
        *,
        source: JobSource,
        country_code: str,
        keyword: str,
    ) -> dict[str, Any] | None:
        return await self._repository.get_active_for_target(
            source=source,
            country_code=country_code,
            keyword=keyword,
        )

    async def cancel_active_run(
        self,
        run_id: str,
        *,
        error_summary: str | None = None,
    ) -> bool:
        return await self._repository.cancel_if_running(run_id, error_summary=error_summary)

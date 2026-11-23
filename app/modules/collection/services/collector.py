import asyncio
import contextlib
import logging
import time
from typing import Any

from app.modules.collection.adapters.base import JobSourceAdapter
from app.modules.collection.http.errors import PublicBoardCollectionError
from app.modules.collection.linkedin.checkpoint_policy import (
    persist_linkedin_run_checkpoint,
    prepare_linkedin_run_checkpoint,
)
from app.modules.collection.linkedin.errors import LinkedInCollectionError, LinkedInFailureState
from app.modules.collection.models.enums import CollectionRunStatus
from app.modules.collection.models.stats import CollectionStats
from app.modules.collection.repositories.checkpoint_repository import CheckpointRepository
from app.modules.collection.repositories.target_repository import TargetRepository, lock_is_active
from app.modules.collection.services.error_handler import CollectionErrorHandler
from app.modules.collection.services.normalizer import JobNormalizationError, JobNormalizer
from app.modules.collection.services.persistence import JobPersistenceService
from app.modules.collection.services.run_service import CollectionRunService
from app.modules.jobs.models.job import JobDataProvenance, JobSource

logger = logging.getLogger(__name__)


class CollectionLockError(RuntimeError):
    pass


class JobCollector:
    def __init__(
        self,
        *,
        adapter: JobSourceAdapter,
        normalizer: JobNormalizer,
        persistence: JobPersistenceService,
        run_service: CollectionRunService,
        checkpoint_repository: CheckpointRepository,
        target_repository: TargetRepository,
        error_handler: CollectionErrorHandler,
        lock_lease_seconds: int = 300,
        adapter_timeout_seconds: int = 60,
        max_adapter_retries: int = 2,
        target_success_cooldown_seconds: int = 0,
        linkedin_access_pause_seconds: int = 86400,
    ) -> None:
        self._adapter = adapter
        self._normalizer = normalizer
        self._persistence = persistence
        self._run_service = run_service
        self._checkpoints = checkpoint_repository
        self._targets = target_repository
        self._errors = error_handler
        self._lock_lease_seconds = lock_lease_seconds
        self._adapter_timeout_seconds = adapter_timeout_seconds
        self._max_adapter_retries = max_adapter_retries
        self._target_cooldown_seconds = target_success_cooldown_seconds
        self._linkedin_access_pause_seconds = linkedin_access_pause_seconds

    _LINKEDIN_PAUSE_STATES = frozenset(
        {
            LinkedInFailureState.VERIFICATION_REQUIRED,
            LinkedInFailureState.AUTHENTICATION_REQUIRED,
            LinkedInFailureState.SESSION_EXPIRED,
            LinkedInFailureState.ACCESS_DENIED,
            LinkedInFailureState.RATE_LIMITED,
        }
    )

    async def collect(
        self,
        *,
        source: JobSource,
        country_code: str,
        keyword: str,
        max_jobs: int,
        dry_run: bool,
        run_owner: str,
        data_provenance: JobDataProvenance | None = None,
        search_location: str | None = None,
        linkedin_ignore_checkpoint: bool = False,
    ) -> dict[str, Any]:
        country_code = country_code.upper()
        keyword = keyword.strip().lower()
        stats = CollectionStats()

        if dry_run:
            result = await self._fetch_and_process(
                source=source,
                country_code=country_code,
                keyword=keyword,
                max_jobs=max_jobs,
                persist=False,
                stats=stats,
                data_provenance=data_provenance,
                search_location=search_location,
                linkedin_ignore_checkpoint=linkedin_ignore_checkpoint,
            )
            return {"run_id": None, "dry_run": True, "stats": stats.model_dump(), **result}

        await self._reconcile_orphaned_active_run(
            source=source,
            country_code=country_code,
            keyword=keyword,
            search_location=search_location,
        )

        active = await self._run_service.get_running(
            source=source,
            country_code=country_code,
            keyword=keyword,
            search_location=search_location,
        )
        if active is not None:
            raise CollectionLockError("Another collection run is already active for this target")

        await self._targets.upsert_target(
            source=source,
            country_code=country_code,
            keyword=keyword,
            search_location=search_location,
        )

        await self._targets.release_stale_lock(
            source=source,
            country_code=country_code,
            keyword=keyword,
            search_location=search_location,
        )

        lock_doc = await self._targets.try_acquire_lock(
            source=source,
            country_code=country_code,
            keyword=keyword,
            owner=run_owner,
            lease_seconds=self._lock_lease_seconds,
            search_location=search_location,
        )
        if lock_doc is None:
            raise CollectionLockError("Could not acquire collection target lock")

        target_id = lock_doc["_id"]
        run = await self._run_service.start(
            source=source,
            country_code=country_code,
            keyword=keyword,
            dry_run=False,
            search_location=search_location,
        )
        run_started = time.monotonic()

        try:
            result = await self._fetch_and_process(
                source=source,
                country_code=country_code,
                keyword=keyword,
                max_jobs=max_jobs,
                persist=True,
                stats=stats,
                data_provenance=data_provenance,
                search_location=search_location,
                linkedin_ignore_checkpoint=linkedin_ignore_checkpoint,
            )
            duration_seconds = round(time.monotonic() - run_started, 2)
            stats_dump = stats.model_dump()
            await self._targets.mark_success(
                target_id,
                cooldown_seconds=self._target_cooldown_seconds,
                last_run_stats={
                    "collected_count": stats_dump.get("collected_count"),
                    "created_count": stats_dump.get("created_count"),
                    "updated_count": stats_dump.get("updated_count"),
                    "rejected_count": stats_dump.get("rejected_count"),
                    "duration_seconds": duration_seconds,
                    "run_id": run.run_id,
                },
            )
            await self._run_service.complete(
                run.run_id,
                status=CollectionRunStatus.COMPLETED,
                stats=stats,
            )
            return {
                "run_id": run.run_id,
                "dry_run": False,
                "stats": stats.model_dump(),
                **result,
            }
        except asyncio.CancelledError:
            await self._run_service.complete(
                run.run_id,
                status=CollectionRunStatus.CANCELLED,
                stats=stats,
                error_summary="cancelled",
            )
            raise
        except Exception as exc:
            error_summary = self._errors.record(exc)
            pause_seconds = max(self._target_cooldown_seconds, 300)
            disable_target = False
            if isinstance(exc, LinkedInCollectionError):
                pause_seconds = max(pause_seconds, self._linkedin_access_pause_seconds)
                disable_target = exc.state in self._LINKEDIN_PAUSE_STATES
                logger.error(
                    "LinkedIn collection halted state=%s disable_target=%s",
                    exc.state.value,
                    disable_target,
                )
            duration_seconds = round(time.monotonic() - run_started, 2)
            await self._targets.mark_failure(
                target_id,
                error_summary=error_summary,
                pause_seconds=pause_seconds,
                disable_target=disable_target,
                last_run_stats={
                    "duration_seconds": duration_seconds,
                    "run_id": run.run_id,
                },
            )
            await self._run_service.complete(
                run.run_id,
                status=CollectionRunStatus.FAILED,
                stats=stats,
                error_summary=error_summary,
            )
            raise
        finally:
            await self._targets.release_lock(target_id, run_owner)

    async def _reconcile_orphaned_active_run(
        self,
        *,
        source: JobSource,
        country_code: str,
        keyword: str,
        search_location: str | None = None,
    ) -> bool:
        active = await self._run_service.get_running(
            source=source,
            country_code=country_code,
            keyword=keyword,
            search_location=search_location,
        )
        if active is None:
            return False
        target = await self._targets.find_target(
            source=source,
            country_code=country_code,
            keyword=keyword,
            search_location=search_location,
        )
        if lock_is_active(target):
            return False
        cancelled = await self._run_service.cancel_active_run(
            active["run_id"],
            error_summary="orphaned_active_run",
        )
        if cancelled:
            logger.warning(
                "Cancelled orphaned collection run run_id=%s source=%s country=%s keyword=%s",
                active["run_id"],
                source.value,
                country_code.upper(),
                keyword.strip().lower(),
            )
        return cancelled

    async def _fetch_and_process(
        self,
        *,
        source: JobSource,
        country_code: str,
        keyword: str,
        max_jobs: int,
        persist: bool,
        stats: CollectionStats,
        data_provenance: JobDataProvenance | None = None,
        search_location: str | None = None,
        linkedin_ignore_checkpoint: bool = False,
    ) -> dict[str, Any]:
        checkpoint = None
        if persist:
            stored = await self._checkpoints.load(
                source=source,
                country_code=country_code,
                keyword=keyword,
                search_location=search_location,
            )
            if source == JobSource.LINKEDIN:
                checkpoint = prepare_linkedin_run_checkpoint(
                    stored,
                    ignore_stored=linkedin_ignore_checkpoint,
                )
            else:
                checkpoint = stored
        adapter_result = await self._fetch_with_retries(
            country_code=country_code,
            keyword=keyword,
            limit=max_jobs,
            checkpoint=checkpoint,
            search_location=search_location,
        )
        stats.collected_count = len(adapter_result.jobs)
        adapter_metrics = dict(adapter_result.metrics or {})
        stats.adapter_rejected_stale = int(adapter_metrics.get("rejected_stale", 0))
        stats.adapter_rejected_unknown_posting = int(
            adapter_metrics.get("rejected_unknown_posting", 0)
        )
        stats.adapter_rejected_location_mismatch = int(
            adapter_metrics.get("rejected_location_mismatch", 0)
        )
        stats.adapter_rejected_keyword_mismatch = int(
            adapter_metrics.get("rejected_keyword_mismatch", 0)
        )
        stats.adapter_rejected_keyword_serp = int(adapter_metrics.get("rejected_keyword_serp", 0))

        normalized_jobs = []
        for raw in adapter_result.jobs:
            try:
                normalized_jobs.append(
                    self._normalizer.normalize(raw, data_provenance=data_provenance)
                )
            except JobNormalizationError as exc:
                stats.rejected_count += 1
                self._errors.record(exc, context={"source_job_id": raw.source_job_id})

        persistence_stats = CollectionStats()
        if persist and normalized_jobs:
            persist_started = time.monotonic()
            logger.info(
                "collection phase=mongo_persist event=start job_count=%s",
                len(normalized_jobs),
            )
            persistence_stats = await self._persistence.persist_jobs(normalized_jobs)
            logger.info(
                "collection phase=mongo_persist event=end duration_ms=%s",
                int((time.monotonic() - persist_started) * 1000),
            )
        checkpoint_out = adapter_result.checkpoint
        if persist:
            checkpoint_out = adapter_result.checkpoint
            if source == JobSource.LINKEDIN:
                checkpoint_out = persist_linkedin_run_checkpoint(adapter_result.checkpoint)
            ck_started = time.monotonic()
            await self._checkpoints.save(
                source=source,
                country_code=country_code,
                keyword=keyword,
                checkpoint=checkpoint_out,
                search_location=search_location,
            )
            logger.info(
                "collection phase=mongo_checkpoint event=end duration_ms=%s",
                int((time.monotonic() - ck_started) * 1000),
            )
        stats.merge(persistence_stats)

        return {
            "checkpoint": checkpoint_out,
            "has_more": adapter_result.has_more,
            "normalized": len(normalized_jobs),
            "adapter_metrics": adapter_metrics,
        }

    async def _fetch_with_retries(
        self,
        *,
        country_code: str,
        keyword: str,
        limit: int,
        checkpoint: dict[str, Any] | None,
        search_location: str | None = None,
    ):
        last_exc: Exception | None = None
        timeout_s = self._adapter_timeout_seconds
        warn_at_s = max(1, int(timeout_s * 0.75))
        logger.info("collection adapter_fetch timeout_budget_s=%s", timeout_s)
        for attempt in range(self._max_adapter_retries + 1):
            started = time.monotonic()

            async def _warn_if_slow() -> None:
                await asyncio.sleep(warn_at_s)
                elapsed = time.monotonic() - started
                if elapsed >= warn_at_s:
                    remaining = max(0, timeout_s - elapsed)
                    logger.warning(
                        "Adapter fetch approaching timeout elapsed_s=%.1f remaining_s=%.1f "
                        "budget_s=%s attempt=%s",
                        elapsed,
                        remaining,
                        timeout_s,
                        attempt + 1,
                    )

            warn_task = asyncio.create_task(_warn_if_slow())
            try:
                try:
                    return await asyncio.wait_for(
                        self._adapter.fetch_jobs(
                            country_code=country_code,
                            keyword=keyword,
                            limit=limit,
                            checkpoint=checkpoint,
                            search_location=search_location,
                        ),
                        timeout=timeout_s,
                    )
                except TimeoutError as exc:
                    logger.error(
                        "Adapter fetch exceeded timeout_seconds=%s attempt=%s",
                        timeout_s,
                        attempt + 1,
                    )
                    last_exc = exc
                    if attempt >= self._max_adapter_retries:
                        break
                    await asyncio.sleep(0.2 * (attempt + 1))
                except (LinkedInCollectionError, PublicBoardCollectionError) as exc:
                    if not exc.retryable:
                        raise
                    last_exc = exc
                    if attempt >= self._max_adapter_retries:
                        break
                    await asyncio.sleep(0.2 * (attempt + 1))
                except Exception as exc:
                    last_exc = exc
                    if attempt >= self._max_adapter_retries:
                        break
                    await asyncio.sleep(0.2 * (attempt + 1))
            finally:
                warn_task.cancel()
                with contextlib.suppress(asyncio.CancelledError):
                    await warn_task
        assert last_exc is not None
        raise last_exc

    async def shutdown(self) -> None:
        shutdown = getattr(self._adapter, "shutdown_browser", None)
        if shutdown is not None:
            await shutdown()
        close_http = getattr(self._adapter, "aclose", None)
        if close_http is not None:
            await close_http()

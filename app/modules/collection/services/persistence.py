import logging

from app.modules.collection.models.enums import JobUpsertOutcome
from app.modules.collection.models.stats import CollectionStats
from app.modules.jobs.models.job import JobDocument
from app.modules.jobs.repositories.job_repository import JobRepository

logger = logging.getLogger(__name__)


class JobPersistenceService:
    def __init__(self, repository: JobRepository) -> None:
        self._repository = repository

    async def persist_jobs(self, jobs: list[JobDocument]) -> CollectionStats:
        stats = CollectionStats()
        for job in jobs:
            try:
                _, outcome = await self._repository.upsert_job_tracked(job)
            except Exception:
                logger.exception(
                    "Job persistence failed source=%s source_job_id=%s",
                    job.source.value,
                    job.source_job_id,
                )
                stats.failed_count += 1
                raise
            if outcome == JobUpsertOutcome.CREATED:
                stats.created_count += 1
            elif outcome == JobUpsertOutcome.UPDATED:
                stats.updated_count += 1
            else:
                stats.unchanged_count += 1
        return stats

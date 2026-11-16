from collections.abc import AsyncGenerator
from typing import Annotated, Any

from fastapi import Depends, Request
from pymongo.asynchronous.database import AsyncDatabase

from app.database.mongodb import get_mongodb
from app.modules.jobs.repositories.job_repository import JobRepository
from app.modules.jobs.services.job_service import JobService


async def get_db() -> AsyncGenerator[AsyncDatabase[Any]]:
    yield get_mongodb().database


def get_job_repository(
    db: Annotated[AsyncDatabase[Any], Depends(get_db)],
) -> JobRepository:
    return JobRepository(db)


def get_job_service(
    repository: Annotated[JobRepository, Depends(get_job_repository)],
) -> JobService:
    return JobService(repository)


async def get_redis_from_request(request: Request):
    return request.app.state.redis

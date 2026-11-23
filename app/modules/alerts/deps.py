"""FastAPI dependencies for job alerts."""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import Depends, HTTPException, Security, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pymongo.asynchronous.database import AsyncDatabase

from app.api.deps import get_db
from app.core.config import Settings, get_settings
from app.modules.alerts.repositories import (
    AlertSubscriberRepository,
    DigestStateRepository,
    NotificationRepository,
    SavedSearchRepository,
)
from app.modules.alerts.subscriber_auth import hash_bearer_token, verify_token_format
from app.modules.jobs.repositories.job_repository import JobRepository

_bearer = HTTPBearer(auto_error=False)


def require_alerts_api(settings: Annotated[Settings, Depends(get_settings)]) -> Settings:
    if not settings.alerts_api_enabled:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Alerts API disabled")
    return settings


async def get_current_subscriber_id(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Security(_bearer)],
    db: Annotated[AsyncDatabase[Any], Depends(get_db)],
) -> str:
    if credentials is None or not credentials.credentials:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Bearer token required")
    token = credentials.credentials
    if not verify_token_format(token):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")
    repo = AlertSubscriberRepository(db)
    doc = await repo.find_by_token_hash(hash_bearer_token(token))
    if doc is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")
    return str(doc["subscriber_id"])


def get_subscriber_repo(db: Annotated[AsyncDatabase[Any], Depends(get_db)]) -> AlertSubscriberRepository:
    return AlertSubscriberRepository(db)


def get_search_repo(db: Annotated[AsyncDatabase[Any], Depends(get_db)]) -> SavedSearchRepository:
    return SavedSearchRepository(db)


def get_notification_repo(db: Annotated[AsyncDatabase[Any], Depends(get_db)]) -> NotificationRepository:
    return NotificationRepository(db)


def get_digest_repo(db: Annotated[AsyncDatabase[Any], Depends(get_db)]) -> DigestStateRepository:
    return DigestStateRepository(db)


def get_job_repo(db: Annotated[AsyncDatabase[Any], Depends(get_db)]) -> JobRepository:
    return JobRepository(db)
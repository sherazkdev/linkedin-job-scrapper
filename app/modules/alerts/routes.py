"""Job alert REST API (in-app channel; push disabled)."""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response, status

from app.core.config import Settings
from app.modules.alerts.deps import (
    get_current_subscriber_id,
    get_digest_repo,
    get_job_repo,
    get_notification_repo,
    get_search_repo,
    get_subscriber_repo,
    require_alerts_api,
)
from app.modules.alerts.digest import DailyDigestService
from app.modules.alerts.repositories import (
    AlertSubscriberRepository,
    DigestStateRepository,
    NotificationRepository,
    SavedSearchRepository,
)
from app.modules.alerts.schemas import (
    MarkReadBody,
    NotificationListOut,
    NotificationOut,
    SavedSearchCreate,
    SavedSearchOut,
    SavedSearchUpdate,
    SubscriberRegisterOut,
)
from app.api.deps import get_redis_from_request
from app.database.redis_client import RedisClient
from app.modules.alerts.subscriber_auth import hash_bearer_token, issue_bearer_token, new_subscriber_id
from app.modules.jobs.repositories.job_repository import JobRepository

router = APIRouter(prefix="/api/v1/alerts", tags=["alerts"])

REGISTER_RATE_KEY = "alerts:register"


def _search_out(doc: dict[str, Any]) -> SavedSearchOut:
    return SavedSearchOut(
        id=str(doc["search_id"]),
        subscriber_id=str(doc["subscriber_id"]),
        q=doc.get("q"),
        country_code=doc.get("country_code"),
        city=doc.get("city"),
        employment_type=doc.get("employment_type"),
        is_remote=doc.get("is_remote"),
        alerts_enabled=bool(doc.get("alerts_enabled", True)),
        digest_enabled=bool(doc.get("digest_enabled", False)),
        digest_local_time=doc.get("digest_local_time"),
        digest_timezone=str(doc.get("digest_timezone") or "UTC"),
        digest_max_jobs=int(doc.get("digest_max_jobs") or 10),
        created_at=doc["created_at"],
        updated_at=doc["updated_at"],
    )


def _notif_out(doc: dict[str, Any]) -> NotificationOut:
    return NotificationOut(
        id=str(doc["_id"]),
        event_key=str(doc["event_key"]),
        job_id=str(doc["job_id"]),
        title=doc.get("title"),
        company=doc.get("company"),
        job_url=doc.get("job_url"),
        read_at=doc.get("read_at"),
        created_at=doc["created_at"],
        payload_type=str(doc.get("payload_type") or "in_app"),
    )


async def _enforce_register_rate_limit(
    request: Request,
    settings: Settings,
    redis_wrap: RedisClient,
) -> None:
    if settings.alerts_register_max_per_ip <= 0:
        return
    client_ip = request.client.host if request.client else "unknown"
    key = f"{REGISTER_RATE_KEY}:{client_ip}"
    try:
        count = await redis_wrap.client.incr(key)
        if count == 1:
            await redis_wrap.client.expire(key, 3600)
        if count > settings.alerts_register_max_per_ip:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="Too many subscriber registrations from this client",
            )
    except HTTPException:
        raise
    except Exception:
        return


def require_digest_enabled(settings: Annotated[Settings, Depends(require_alerts_api)]) -> Settings:
    if not settings.alerts_digest_enabled:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Daily digest disabled")
    return settings


@router.post("/subscribers/register", response_model=SubscriberRegisterOut)
async def register_subscriber(
    request: Request,
    settings: Annotated[Settings, Depends(require_alerts_api)],
    repo: Annotated[AlertSubscriberRepository, Depends(get_subscriber_repo)],
    redis_wrap: Annotated[RedisClient, Depends(get_redis_from_request)],
) -> SubscriberRegisterOut:
    await _enforce_register_rate_limit(request, settings, redis_wrap)
    token = issue_bearer_token()
    subscriber_id = new_subscriber_id()
    await repo.create(subscriber_id=subscriber_id, token_hash=hash_bearer_token(token))
    return SubscriberRegisterOut(subscriber_id=subscriber_id, bearer_token=token)


@router.get("/searches", response_model=list[SavedSearchOut])
async def list_searches(
    subscriber_id: Annotated[str, Depends(get_current_subscriber_id)],
    repo: Annotated[SavedSearchRepository, Depends(get_search_repo)],
) -> list[SavedSearchOut]:
    docs = await repo.list_for_subscriber(subscriber_id)
    return [_search_out(d) for d in docs]


@router.post("/searches", response_model=SavedSearchOut, status_code=status.HTTP_201_CREATED)
async def create_search(
    body: SavedSearchCreate,
    subscriber_id: Annotated[str, Depends(get_current_subscriber_id)],
    repo: Annotated[SavedSearchRepository, Depends(get_search_repo)],
) -> SavedSearchOut:
    doc = await repo.create(subscriber_id=subscriber_id, payload=body.model_dump())
    return _search_out(doc)


@router.patch("/searches/{search_id}", response_model=SavedSearchOut)
async def update_search(
    search_id: str,
    body: SavedSearchUpdate,
    subscriber_id: Annotated[str, Depends(get_current_subscriber_id)],
    repo: Annotated[SavedSearchRepository, Depends(get_search_repo)],
) -> SavedSearchOut:
    updates = {k: v for k, v in body.model_dump().items() if v is not None}
    if "employment_type" in updates and updates["employment_type"] is not None:
        updates["employment_type"] = updates["employment_type"].value
    doc = await repo.update_owned(subscriber_id=subscriber_id, search_id=search_id, updates=updates)
    if doc is None:
        raise HTTPException(status_code=404, detail="Saved search not found")
    return _search_out(doc)


@router.delete(
    "/searches/{search_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    response_class=Response,
)
async def delete_search(
    search_id: str,
    subscriber_id: Annotated[str, Depends(get_current_subscriber_id)],
    repo: Annotated[SavedSearchRepository, Depends(get_search_repo)],
) -> Response:
    if not await repo.delete_owned(subscriber_id=subscriber_id, search_id=search_id):
        raise HTTPException(status_code=404, detail="Saved search not found")
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/searches/{search_id}/enable", response_model=SavedSearchOut)
async def enable_search(
    search_id: str,
    subscriber_id: Annotated[str, Depends(get_current_subscriber_id)],
    repo: Annotated[SavedSearchRepository, Depends(get_search_repo)],
) -> SavedSearchOut:
    doc = await repo.update_owned(
        subscriber_id=subscriber_id, search_id=search_id, updates={"enabled": True, "alerts_enabled": True}
    )
    if doc is None:
        raise HTTPException(status_code=404, detail="Saved search not found")
    return _search_out(doc)


@router.post("/searches/{search_id}/disable", response_model=SavedSearchOut)
async def disable_search(
    search_id: str,
    subscriber_id: Annotated[str, Depends(get_current_subscriber_id)],
    repo: Annotated[SavedSearchRepository, Depends(get_search_repo)],
) -> SavedSearchOut:
    doc = await repo.update_owned(
        subscriber_id=subscriber_id,
        search_id=search_id,
        updates={"enabled": False, "alerts_enabled": False},
    )
    if doc is None:
        raise HTTPException(status_code=404, detail="Saved search not found")
    return _search_out(doc)


@router.get("/notifications", response_model=NotificationListOut)
async def list_notifications(
    subscriber_id: Annotated[str, Depends(get_current_subscriber_id)],
    repo: Annotated[NotificationRepository, Depends(get_notification_repo)],
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    unread_only: bool = False,
) -> NotificationListOut:
    items, total, unread = await repo.list_for_subscriber(
        subscriber_id=subscriber_id,
        page=page,
        page_size=page_size,
        unread_only=unread_only,
    )
    return NotificationListOut(
        items=[_notif_out(d) for d in items],
        total=total,
        page=page,
        page_size=page_size,
        unread_count=unread,
    )


@router.get("/notifications/unread-count")
async def unread_count(
    subscriber_id: Annotated[str, Depends(get_current_subscriber_id)],
    repo: Annotated[NotificationRepository, Depends(get_notification_repo)],
) -> dict[str, int]:
    _, _, unread = await repo.list_for_subscriber(
        subscriber_id=subscriber_id, page=1, page_size=1, unread_only=False
    )
    return {"unread_count": unread}


@router.post("/notifications/mark-read")
async def mark_read(
    body: MarkReadBody,
    subscriber_id: Annotated[str, Depends(get_current_subscriber_id)],
    repo: Annotated[NotificationRepository, Depends(get_notification_repo)],
) -> dict[str, int]:
    n = await repo.mark_read(
        subscriber_id=subscriber_id,
        notification_ids=body.notification_ids,
        mark_all=body.mark_all,
    )
    return {"marked": n}


@router.delete(
    "/notifications/{notification_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    response_class=Response,
)
async def dismiss_notification(
    notification_id: str,
    subscriber_id: Annotated[str, Depends(get_current_subscriber_id)],
    repo: Annotated[NotificationRepository, Depends(get_notification_repo)],
) -> Response:
    if not await repo.dismiss(subscriber_id=subscriber_id, notification_id=notification_id):
        raise HTTPException(status_code=404, detail="Notification not found")
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/digest/run")
async def run_digest_once(
    settings: Annotated[Settings, Depends(require_digest_enabled)],
    subscriber_id: Annotated[str, Depends(get_current_subscriber_id)],
    searches: Annotated[SavedSearchRepository, Depends(get_search_repo)],
    notifications: Annotated[NotificationRepository, Depends(get_notification_repo)],
    digest_state: Annotated[DigestStateRepository, Depends(get_digest_repo)],
    jobs: Annotated[JobRepository, Depends(get_job_repo)],
) -> dict[str, Any]:
    """Manual/idempotent digest trigger (no Beat). Requires ALERTS_DIGEST_ENABLED."""
    svc = DailyDigestService(
        searches=searches,
        notifications=notifications,
        digest_state=digest_state,
        jobs=jobs,
        settings=settings,
    )
    return await svc.run_for_subscriber(subscriber_id)
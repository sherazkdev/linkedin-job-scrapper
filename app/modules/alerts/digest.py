"""Daily in-app digest (idempotent, timezone-aware)."""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import Any
from zoneinfo import ZoneInfo

from app.core.config import Settings
from app.modules.alerts.constants import EVENT_DIGEST
from app.modules.alerts.matcher import job_matches_saved_search
from app.modules.alerts.repositories import (
    DigestStateRepository,
    NotificationRepository,
    SavedSearchRepository,
)
from app.modules.jobs.repositories.job_repository import JobRepository

logger = logging.getLogger(__name__)


def digest_key_for_local_date(*, tz_name: str, now: datetime | None = None) -> str:
    now = now or datetime.now(UTC)
    try:
        local = now.astimezone(ZoneInfo(tz_name))
    except Exception:
        local = now.astimezone(ZoneInfo("UTC"))
    return local.strftime("%Y-%m-%d")


class DailyDigestService:
    def __init__(
        self,
        *,
        searches: SavedSearchRepository,
        notifications: NotificationRepository,
        digest_state: DigestStateRepository,
        jobs: JobRepository,
        settings: Settings,
    ) -> None:
        self._searches = searches
        self._notifications = notifications
        self._digest_state = digest_state
        self._jobs = jobs
        self._settings = settings

    async def run_for_subscriber(self, subscriber_id: str) -> dict[str, Any]:
        if not self._settings.alerts_digest_enabled:
            return {"status": "disabled", "created": 0}
        searches = [
            s for s in await self._searches.list_for_subscriber(subscriber_id) if s.get("digest_enabled")
        ]
        if not searches:
            return {"status": "no_digest_searches", "created": 0}
        tz = str(searches[0].get("digest_timezone") or "UTC")
        key = digest_key_for_local_date(tz_name=tz)
        if await self._digest_state.already_sent(subscriber_id=subscriber_id, digest_key=key):
            return {"status": "idempotent_skip", "digest_key": key, "created": 0}
        max_jobs = min(int(searches[0].get("digest_max_jobs") or 10), 50)
        max_age = self._settings.job_public_listing_max_age_days
        created = 0
        seen_jobs: set[str] = set()
        for search in searches:
            # Pull recent eligible jobs and match (no live collection).
            filters_query = {"status": "active"}
            if search.get("country_code"):
                cc = str(search["country_code"]).upper()
                filters_query = {
                    "$and": [
                        {"status": "active"},
                        {"$or": [{"country_code": cc}, {"search_country_code": cc}]},
                    ]
                }
            collection = self._jobs._collection  # noqa: SLF001
            jobs_batch = await collection.find(filters_query).sort("posted_at", -1).limit(200).to_list(
                200
            )
            for job in jobs_batch:
                jid = str(job.get("_id"))
                if jid in seen_jobs:
                    continue
                if not job_matches_saved_search(job, search, max_age_days=max_age):
                    continue
                seen_jobs.add(jid)
                doc = await self._notifications.insert_in_app(
                    subscriber_id=subscriber_id,
                    job_id=jid,
                    event_key=f"{EVENT_DIGEST}:{key}",
                    job_snapshot={
                        "title": job.get("title"),
                        "company": job.get("company"),
                        "job_url": job.get("job_url"),
                    },
                )
                if doc is not None:
                    created += 1
                if created >= max_jobs:
                    break
            if created >= max_jobs:
                break
        await self._digest_state.upsert_sent(subscriber_id=subscriber_id, digest_key=key)
        return {"status": "ok", "digest_key": key, "created": created}
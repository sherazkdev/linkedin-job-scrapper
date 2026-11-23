"""Daily in-app digest — subscriber-level schedule, idempotent delivery."""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import Any

from app.core.config import Settings
from app.modules.alerts.digest_schedule import (
    digest_event_key,
    digest_local_date_key,
    is_past_scheduled_time,
    schedule_from_digest_state,
)
from app.modules.alerts.matcher import job_matches_saved_search
from app.modules.alerts.repositories import (
    DigestDeliveryRepository,
    DigestStateRepository,
    NotificationRepository,
    SavedSearchRepository,
)
from app.modules.jobs.repositories.job_repository import JobRepository

logger = logging.getLogger(__name__)


class DailyDigestService:
    """
    Delivery policy: **one digest schedule per subscriber** (timezone + local time + max jobs)
    stored in `alert_digest_state`. Saved searches only opt in via `digest_enabled` and define
    which job filters are merged into the daily bundle.

    Manual preview (`preview=True`) skips clock enforcement and does not claim delivery slots.
    """

    def __init__(
        self,
        *,
        searches: SavedSearchRepository,
        notifications: NotificationRepository,
        digest_state: DigestStateRepository,
        digest_delivery: DigestDeliveryRepository,
        jobs: JobRepository,
        settings: Settings,
    ) -> None:
        self._searches = searches
        self._notifications = notifications
        self._digest_state = digest_state
        self._digest_delivery = digest_delivery
        self._jobs = jobs
        self._settings = settings

    async def run_for_subscriber(
        self,
        subscriber_id: str,
        *,
        preview: bool = False,
        now: datetime | None = None,
    ) -> dict[str, Any]:
        if not self._settings.alerts_digest_enabled:
            return {"status": "disabled", "created": 0}
        state = await self._digest_state.get(subscriber_id)
        schedule = schedule_from_digest_state(state)
        if schedule is None:
            return {"status": "no_digest_schedule", "created": 0}

        search_docs = [
            s
            for s in await self._searches.list_for_subscriber(subscriber_id)
            if s.get("enabled")
            and s.get("digest_enabled")
            and s.get("alerts_enabled")
        ]
        if not search_docs:
            return {"status": "no_digest_searches", "created": 0}

        if not preview and not is_past_scheduled_time(schedule=schedule, now=now):
            return {
                "status": "not_due",
                "digest_timezone": schedule.timezone,
                "digest_local_time": schedule.local_time,
                "created": 0,
            }

        date_key = digest_local_date_key(tz_name=schedule.timezone, now=now)
        event_key = digest_event_key(tz_name=schedule.timezone, now=now, preview=preview)

        if not preview:
            claimed = await self._digest_delivery.try_claim(
                subscriber_id=subscriber_id,
                digest_key=date_key,
            )
            if not claimed:
                return {"status": "idempotent_skip", "digest_key": date_key, "created": 0}

        max_jobs = min(schedule.max_jobs, 50)
        max_age = self._settings.job_public_listing_max_age_days
        created = 0
        seen_jobs: set[str] = set()
        collection = self._jobs._collection  # noqa: SLF001

        for search in search_docs:
            filters_query: dict[str, Any] = {"status": "active"}
            if search.get("country_code"):
                cc = str(search["country_code"]).upper()
                filters_query = {
                    "$and": [
                        {"status": "active"},
                        {"$or": [{"country_code": cc}, {"search_country_code": cc}]},
                    ]
                }
            cursor = collection.find(filters_query).sort("posted_at", -1).limit(200)
            jobs_batch = await cursor.to_list(length=200)
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
                    event_key=event_key,
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

        if not preview:
            await self._digest_state.upsert_sent(subscriber_id=subscriber_id, digest_key=date_key)

        return {
            "status": "ok" if created else "empty",
            "digest_key": date_key,
            "preview": preview,
            "created": created,
        }
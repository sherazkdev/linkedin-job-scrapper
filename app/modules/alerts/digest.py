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
    stored in `alert_digest_state`. Saved searches only opt in via `digest_enabled`.

    Preview is read-only: zero writes to notifications, deliveries, or digest_state.
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

    async def _eligible_jobs(
        self,
        *,
        subscriber_id: str,
        schedule_max_jobs: int,
        now: datetime | None,
    ) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
        search_docs = [
            s
            for s in await self._searches.list_for_subscriber(subscriber_id)
            if s.get("enabled")
            and s.get("digest_enabled")
            and s.get("alerts_enabled")
        ]
        if not search_docs:
            return search_docs, []

        max_jobs = min(schedule_max_jobs, 50)
        max_age = self._settings.job_public_listing_max_age_days
        results: list[dict[str, Any]] = []
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
                results.append(
                    {
                        "job_id": jid,
                        "title": job.get("title"),
                        "company": job.get("company"),
                        "country_code": job.get("country_code") or job.get("search_country_code"),
                        "city": job.get("city"),
                        "job_url": job.get("job_url"),
                    }
                )
                if len(results) >= max_jobs:
                    break
            if len(results) >= max_jobs:
                break
        return search_docs, results

    async def run_for_subscriber(
        self,
        subscriber_id: str,
        *,
        preview: bool = False,
        now: datetime | None = None,
    ) -> dict[str, Any]:
        if not self._settings.alerts_digest_enabled:
            return {"status": "disabled", "created": 0, "preview": preview}

        state = await self._digest_state.get(subscriber_id)
        schedule = schedule_from_digest_state(state)
        if schedule is None:
            return {"status": "no_digest_schedule", "created": 0, "preview": preview}

        if not preview and not is_past_scheduled_time(schedule=schedule, now=now):
            return {
                "status": "not_due",
                "digest_timezone": schedule.timezone,
                "digest_local_time": schedule.local_time,
                "created": 0,
                "preview": False,
            }

        date_key = digest_local_date_key(tz_name=schedule.timezone, now=now)
        _, eligible = await self._eligible_jobs(
            subscriber_id=subscriber_id,
            schedule_max_jobs=schedule.max_jobs,
            now=now,
        )

        if preview:
            return {
                "status": "preview",
                "digest_key": date_key,
                "preview": True,
                "eligible_count": len(eligible),
                "jobs": eligible,
                "created": 0,
            }

        if not eligible:
            if await self._digest_delivery.try_begin_processing(
                subscriber_id=subscriber_id, digest_key=date_key
            ):
                await self._digest_delivery.mark_completed(
                    subscriber_id=subscriber_id,
                    digest_key=date_key,
                    notification_count=0,
                )
                await self._digest_state.upsert_sent(subscriber_id=subscriber_id, digest_key=date_key)
            return {
                "status": "empty",
                "digest_key": date_key,
                "preview": False,
                "created": 0,
            }

        if not await self._digest_delivery.try_begin_processing(
            subscriber_id=subscriber_id, digest_key=date_key
        ):
            return {"status": "idempotent_skip", "digest_key": date_key, "created": 0, "preview": False}

        event_key = digest_event_key(tz_name=schedule.timezone, now=now, preview=False)
        created = 0
        try:
            for row in eligible:
                doc = await self._notifications.insert_in_app(
                    subscriber_id=subscriber_id,
                    job_id=row["job_id"],
                    event_key=event_key,
                    job_snapshot={
                        "title": row.get("title"),
                        "company": row.get("company"),
                        "job_url": row.get("job_url"),
                    },
                )
                if doc is not None:
                    created += 1
            await self._digest_delivery.mark_completed(
                subscriber_id=subscriber_id,
                digest_key=date_key,
                notification_count=created,
            )
            await self._digest_state.upsert_sent(subscriber_id=subscriber_id, digest_key=date_key)
        except Exception:
            await self._digest_delivery.mark_failed(
                subscriber_id=subscriber_id, digest_key=date_key
            )
            raise

        return {
            "status": "ok" if created else "empty",
            "digest_key": date_key,
            "preview": False,
            "created": created,
        }
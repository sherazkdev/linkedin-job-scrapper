"""Generate in-app notifications when persisted jobs match saved searches."""

from __future__ import annotations

import logging
from typing import Any

from app.core.config import Settings
from app.modules.alerts.matcher import event_key_for_outcome, job_matches_saved_search
from app.modules.alerts.repositories import NotificationRepository, SavedSearchRepository
from app.modules.collection.models.enums import JobUpsertOutcome

logger = logging.getLogger(__name__)


class AlertProcessor:
    def __init__(
        self,
        *,
        searches: SavedSearchRepository,
        notifications: NotificationRepository,
        settings: Settings,
    ) -> None:
        self._searches = searches
        self._notifications = notifications
        self._settings = settings

    async def process_job_persisted(
        self,
        job_doc: dict[str, Any],
        *,
        outcome: JobUpsertOutcome,
        reactivated: bool = False,
    ) -> int:
        if not self._settings.alerts_matching_enabled:
            return 0
        if outcome == JobUpsertOutcome.UNCHANGED and not reactivated:
            return 0
        if outcome not in {
            JobUpsertOutcome.CREATED,
            JobUpsertOutcome.UPDATED,
            JobUpsertOutcome.UNCHANGED,
        }:
            return 0
        created = outcome == JobUpsertOutcome.CREATED
        event_key = event_key_for_outcome(created=created, reactivated=reactivated)
        if job_doc.get("_id") is not None:
            job_id = str(job_doc["_id"])
        else:
            job_id = str(job_doc.get("sourceJobId", ""))
        if not job_id:
            return 0
        max_age = self._settings.job_public_listing_max_age_days
        searches = await self._searches.list_alert_enabled()
        sent = 0
        for search in searches:
            if search.get("subscriber_id") is None:
                continue
            if not job_matches_saved_search(job_doc, search, max_age_days=max_age):
                continue
            doc = await self._notifications.insert_in_app(
                subscriber_id=str(search["subscriber_id"]),
                job_id=job_id,
                event_key=event_key,
                job_snapshot={
                    "title": job_doc.get("title"),
                    "company": job_doc.get("company"),
                    "job_url": job_doc.get("job_url"),
                },
            )
            if doc is not None:
                sent += 1
        if sent:
            logger.info(
                "Alerts created count=%s job_id=%s outcome=%s",
                sent,
                job_id,
                outcome.value,
            )
        return sent
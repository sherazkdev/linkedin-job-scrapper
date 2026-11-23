"""Deduplicated job alert events — delivery adapters plug in when configured."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from app.modules.jobs.models.job import JobStatus
from app.modules.jobs.public_visibility import is_publicly_listable


def job_eligible_for_alert(doc: dict[str, Any], *, max_age_days: int = 7) -> bool:
    if str(doc.get("status") or "") != JobStatus.ACTIVE.value:
        return False
    return is_publicly_listable(doc, max_age_days=max_age_days)


def dedupe_alert_event(
    *,
    subscriber_id: str,
    job_id: str,
    event_key: str,
    seen_events: set[str],
) -> dict[str, Any] | None:
    """
    event_key should be stable per (subscriber, job) first-notification.
    Returns delivery payload or None when duplicate.
    """
    composite = f"{subscriber_id}:{event_key}:{job_id}"
    if composite in seen_events:
        return None
    seen_events.add(composite)
    return {
        "subscriber_id": subscriber_id,
        "job_id": job_id,
        "event_key": event_key,
        "created_at": datetime.now(UTC).isoformat(),
        "channel": "in_app",
        "status": "pending",
        "note": "Push delivery requires PUSH_DEVICE_TOKEN and provider credentials.",
    }
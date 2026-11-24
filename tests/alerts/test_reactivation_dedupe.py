from unittest.mock import AsyncMock, MagicMock

import pytest

from app.modules.alerts.constants import EVENT_REACTIVATED
from app.modules.alerts.processor import AlertProcessor
from app.modules.collection.models.enums import JobUpsertOutcome
from app.modules.jobs.models.job import JobStatus


@pytest.mark.asyncio
async def test_reactivation_notifies_once_per_job() -> None:
    settings = MagicMock()
    settings.alerts_matching_enabled = True
    settings.job_public_listing_max_age_days = 7
    searches = AsyncMock()
    searches.list_alert_enabled.return_value = [
        {"subscriber_id": "s1", "enabled": True, "alerts_enabled": True, "country_code": "PK"}
    ]
    notifications = AsyncMock()
    notifications.insert_in_app.side_effect = [{"_id": "n1"}, None]
    proc = AlertProcessor(searches=searches, notifications=notifications, settings=settings)
    job = {
        "_id": "507f1f77bcf86cd799439011",
        "status": JobStatus.ACTIVE.value,
        "title": "Engineer",
        "company": "Co",
        "country_code": "PK",
        "posted_at": __import__("datetime").datetime.now(__import__("datetime").UTC),
        "first_seen_at": __import__("datetime").datetime.now(__import__("datetime").UTC),
    }
    first = await proc.process_job_persisted(
        job, outcome=JobUpsertOutcome.UNCHANGED, reactivated=True
    )
    second = await proc.process_job_persisted(
        job, outcome=JobUpsertOutcome.UNCHANGED, reactivated=True
    )
    assert first == 1
    assert second == 0
    assert notifications.insert_in_app.await_args_list[0].kwargs["event_key"] == EVENT_REACTIVATED
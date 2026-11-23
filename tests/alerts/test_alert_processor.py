from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.modules.alerts.processor import AlertProcessor
from app.modules.collection.models.enums import JobUpsertOutcome
from app.modules.jobs.models.job import JobStatus


def _settings(*, matching: bool) -> MagicMock:
    mock = MagicMock()
    mock.alerts_matching_enabled = matching
    mock.job_public_listing_max_age_days = 7
    return mock


def _job_doc():
    return {
        "_id": "507f1f77bcf86cd799439011",
        "status": JobStatus.ACTIVE.value,
        "title": "Backend Engineer",
        "company": "Acme",
        "country_code": "PK",
        "posted_at": datetime.now(UTC) - timedelta(hours=1),
        "first_seen_at": datetime.now(UTC) - timedelta(hours=1),
        "job_url": "https://example.com/j/1",
    }


@pytest.mark.asyncio
async def test_processor_skips_when_matching_disabled() -> None:
    proc = AlertProcessor(
        searches=AsyncMock(),
        notifications=AsyncMock(),
        settings=_settings(matching=False),
    )
    n = await proc.process_job_persisted(_job_doc(), outcome=JobUpsertOutcome.CREATED)
    assert n == 0


@pytest.mark.asyncio
async def test_processor_skips_unchanged_not_reactivated() -> None:
    proc = AlertProcessor(
        searches=AsyncMock(),
        notifications=AsyncMock(),
        settings=_settings(matching=True),
    )
    n = await proc.process_job_persisted(
        _job_doc(), outcome=JobUpsertOutcome.UNCHANGED, reactivated=False
    )
    assert n == 0


@pytest.mark.asyncio
async def test_processor_creates_on_created() -> None:
    searches = AsyncMock()
    searches.list_alert_enabled.return_value = [
        {
            "subscriber_id": "sub-a",
            "enabled": True,
            "alerts_enabled": True,
            "country_code": "PK",
        }
    ]
    notifications = AsyncMock()
    notifications.insert_in_app.return_value = {"_id": "n1"}
    proc = AlertProcessor(searches=searches, notifications=notifications, settings=_settings(matching=True))
    n = await proc.process_job_persisted(_job_doc(), outcome=JobUpsertOutcome.CREATED)
    assert n == 1
    notifications.insert_in_app.assert_awaited_once()
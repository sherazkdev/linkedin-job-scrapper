from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.modules.alerts.digest import DailyDigestService
from app.modules.alerts.digest_schedule import DigestSchedule


def _settings() -> MagicMock:
    m = MagicMock()
    m.alerts_digest_enabled = True
    m.job_public_listing_max_age_days = 7
    return m


@pytest.mark.asyncio
async def test_preview_writes_nothing() -> None:
    digest_state = AsyncMock()
    digest_state.get.return_value = {
        "digest_timezone": "UTC",
        "digest_local_time": "00:00",
        "digest_max_jobs": 5,
    }
    searches = AsyncMock()
    searches.list_for_subscriber.return_value = [
        {
            "enabled": True,
            "digest_enabled": True,
            "alerts_enabled": True,
            "country_code": "PK",
            "q": "Software",
        }
    ]
    notifications = AsyncMock()
    digest_delivery = AsyncMock()
    jobs = MagicMock()

    svc = DailyDigestService(
        searches=searches,
        notifications=notifications,
        digest_state=digest_state,
        digest_delivery=digest_delivery,
        jobs=jobs,
        settings=_settings(),
    )
    svc._eligible_jobs = AsyncMock(  # noqa: SLF001
        return_value=(
            [{"enabled": True}],
            [{"job_id": "j1", "title": "Software Engineer", "company": "Acme"}],
        )
    )
    result = await svc.run_for_subscriber("sub-1", preview=True)
    assert result["status"] == "preview"
    assert result["eligible_count"] == 1
    notifications.insert_in_app.assert_not_called()
    digest_delivery.try_begin_processing.assert_not_called()
    digest_state.upsert_sent.assert_not_called()


@pytest.mark.asyncio
async def test_preview_repeat_is_side_effect_free() -> None:
    digest_state = AsyncMock()
    digest_state.get.return_value = {
        "digest_timezone": "UTC",
        "digest_local_time": "00:00",
        "digest_max_jobs": 5,
    }
    searches = AsyncMock()
    searches.list_for_subscriber.return_value = []
    notifications = AsyncMock()
    digest_delivery = AsyncMock()
    jobs = MagicMock()
    jobs._collection = AsyncMock()

    svc = DailyDigestService(
        searches=searches,
        notifications=notifications,
        digest_state=digest_state,
        digest_delivery=digest_delivery,
        jobs=jobs,
        settings=_settings(),
    )
    await svc.run_for_subscriber("sub-1", preview=True)
    await svc.run_for_subscriber("sub-1", preview=True)
    notifications.insert_in_app.assert_not_called()
    digest_delivery.try_begin_processing.assert_not_called()
from datetime import UTC, datetime

import pytest

from app.modules.alerts.digest_schedule import (
    digest_local_date_key,
    is_past_scheduled_time,
    schedule_conflicts,
    schedule_from_digest_state,
)
from app.modules.alerts.digest_schedule import DigestSchedule


def test_schedule_from_state() -> None:
    sched = schedule_from_digest_state(
        {
            "digest_timezone": "Asia/Karachi",
            "digest_local_time": "09:00",
            "digest_max_jobs": 5,
        }
    )
    assert sched is not None
    assert sched.timezone == "Asia/Karachi"


def test_schedule_conflict() -> None:
    a = DigestSchedule(timezone="UTC", local_time="09:00", max_jobs=10)
    b = DigestSchedule(timezone="Asia/Karachi", local_time="09:00", max_jobs=10)
    assert schedule_conflicts(a, b)


def test_is_past_scheduled_time() -> None:
    schedule = DigestSchedule(timezone="UTC", local_time="00:00", max_jobs=5)
    noon = datetime(2026, 6, 15, 12, 0, tzinfo=UTC)
    assert is_past_scheduled_time(schedule=schedule, now=noon)


def test_digest_local_date_key_tz() -> None:
    instant = datetime(2026, 6, 15, 22, 0, tzinfo=UTC)
    key = digest_local_date_key(tz_name="Asia/Karachi", now=instant)
    assert len(key) == 10


def test_invalid_timezone_rejected() -> None:
    from app.modules.alerts.timezone_validators import validate_iana_timezone

    with pytest.raises(ValueError):
        validate_iana_timezone("Not/AZone")
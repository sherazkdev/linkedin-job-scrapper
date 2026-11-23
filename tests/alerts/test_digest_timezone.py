from datetime import UTC, datetime

from app.modules.alerts.digest_schedule import digest_local_date_key


def test_digest_key_uses_local_date() -> None:
    instant = datetime(2026, 6, 15, 22, 0, tzinfo=UTC)
    key = digest_local_date_key(tz_name="Asia/Karachi", now=instant)
    assert len(key) == 10
    assert key.count("-") == 2
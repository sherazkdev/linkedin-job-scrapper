import pytest

from app.modules.alerts.push_provider import PushNotificationProvider


@pytest.mark.asyncio
async def test_push_disabled_by_default() -> None:
    provider = PushNotificationProvider(enabled=False)
    result = await provider.send(device_token="x", payload={"title": "t"})
    assert not result.attempted
    assert not result.delivered
    assert result.reason == "push_disabled"
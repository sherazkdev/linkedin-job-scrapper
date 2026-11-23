"""Push delivery abstraction — disabled until provider credentials are configured."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(slots=True)
class PushDeliveryResult:
    attempted: bool
    delivered: bool
    reason: str


class PushNotificationProvider:
    """FCM/APNs integration point (not configured in this release)."""

    def __init__(self, *, enabled: bool = False) -> None:
        self._enabled = enabled

    @property
    def enabled(self) -> bool:
        return self._enabled

    async def send(self, *, device_token: str, payload: dict[str, Any]) -> PushDeliveryResult:
        if not self._enabled:
            return PushDeliveryResult(
                attempted=False,
                delivered=False,
                reason="push_disabled",
            )
        if not device_token:
            return PushDeliveryResult(
                attempted=False,
                delivered=False,
                reason="missing_device_token",
            )
        return PushDeliveryResult(
            attempted=False,
            delivered=False,
            reason="provider_not_configured",
        )
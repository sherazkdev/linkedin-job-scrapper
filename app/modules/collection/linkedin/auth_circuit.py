"""Collection pause decisions for auth/verification (no automatic login)."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum

from app.modules.collection.linkedin.errors import LinkedInFailureState
from app.modules.collection.operations.failure_classifier import (
    CollectionFailureKind,
    classify_error_summary,
    is_auth_or_verification,
)


class CollectionAuthMode(StrEnum):
    HEALTHY = "HEALTHY"
    PAUSED_AUTH = "PAUSED_AUTH"
    PAUSED_VERIFICATION = "PAUSED_VERIFICATION"
    PAUSED_ACCESS = "PAUSED_ACCESS"


@dataclass(slots=True)
class AuthCircuitDecision:
    mode: CollectionAuthMode
    pause_live_requests: bool
    failure_kind: CollectionFailureKind
    linkedin_state: LinkedInFailureState | None
    message: str


_LINKEDIN_STATE_TO_KIND: dict[LinkedInFailureState, CollectionFailureKind] = {
    LinkedInFailureState.AUTHENTICATION_REQUIRED: CollectionFailureKind.AUTH_REQUIRED,
    LinkedInFailureState.SESSION_EXPIRED: CollectionFailureKind.AUTH_REQUIRED,
    LinkedInFailureState.VERIFICATION_REQUIRED: CollectionFailureKind.VERIFICATION_REQUIRED,
    LinkedInFailureState.ACCESS_DENIED: CollectionFailureKind.ACCESS_RESTRICTED,
    LinkedInFailureState.RATE_LIMITED: CollectionFailureKind.ACCESS_RESTRICTED,
}


def decision_from_linkedin_error(exc: Exception) -> AuthCircuitDecision:
    from app.modules.collection.linkedin.errors import LinkedInCollectionError

    if isinstance(exc, LinkedInCollectionError):
        kind = _LINKEDIN_STATE_TO_KIND.get(exc.state, CollectionFailureKind.UNKNOWN)
        if exc.state == LinkedInFailureState.VERIFICATION_REQUIRED:
            mode = CollectionAuthMode.PAUSED_VERIFICATION
        elif kind == CollectionFailureKind.AUTH_REQUIRED:
            mode = CollectionAuthMode.PAUSED_AUTH
        elif kind == CollectionFailureKind.ACCESS_RESTRICTED:
            mode = CollectionAuthMode.PAUSED_ACCESS
        else:
            mode = CollectionAuthMode.PAUSED_AUTH
        return AuthCircuitDecision(
            mode=mode,
            pause_live_requests=True,
            failure_kind=kind,
            linkedin_state=exc.state,
            message=str(exc),
        )
    kind = classify_error_summary(str(exc))
    pause = is_auth_or_verification(kind) or kind in {
        CollectionFailureKind.ACCESS_RESTRICTED,
        CollectionFailureKind.DAILY_CAP,
    }
    mode = CollectionAuthMode.HEALTHY
    if kind == CollectionFailureKind.VERIFICATION_REQUIRED:
        mode = CollectionAuthMode.PAUSED_VERIFICATION
    elif kind == CollectionFailureKind.AUTH_REQUIRED:
        mode = CollectionAuthMode.PAUSED_AUTH
    elif kind == CollectionFailureKind.ACCESS_RESTRICTED:
        mode = CollectionAuthMode.PAUSED_ACCESS
    return AuthCircuitDecision(
        mode=mode,
        pause_live_requests=pause,
        failure_kind=kind,
        linkedin_state=None,
        message=str(exc),
    )


def session_epoch_iso(path: str | Path) -> str | None:
    import json
    from pathlib import Path

    p = Path(path)
    if not p.is_file():
        return None
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
        return str(data.get("session_epoch_at") or "") or None
    except (OSError, json.JSONDecodeError, TypeError):
        return None


def auth_fail_query_since(*, session_epoch_file: str, rolling_seconds: int = 86400) -> datetime:
    """Operator session refresh resets rolling auth-fail window."""
    epoch = session_epoch_iso(session_epoch_file)
    if epoch:
        try:
            return datetime.fromisoformat(epoch.replace("Z", "+00:00"))
        except ValueError:
            pass
    return datetime.now(UTC).replace(microsecond=0) - __import__("datetime").timedelta(
        seconds=rolling_seconds
    )
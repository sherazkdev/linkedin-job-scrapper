import json
import logging
import os
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from app.modules.collection.linkedin.errors import LinkedInCollectionError, LinkedInFailureState
from app.modules.collection.linkedin.session_validation import (
    OfflineSessionQuality,
    inspect_offline_storage_state,
)

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class LinkedInSessionStatus:
    exists: bool
    path: str
    readable: bool
    cookie_count: int
    updated_at: datetime | None
    message: str
    offline_quality: str
    has_li_at: bool
    online_verified: bool
    claims_authenticated: bool

    def to_dict(self) -> dict[str, Any]:
        return {
            "exists": self.exists,
            "path": self.path,
            "readable": self.readable,
            "cookie_count": self.cookie_count,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
            "message": self.message,
            "offline_quality": self.offline_quality,
            "has_li_at": self.has_li_at,
            "online_verified": self.online_verified,
            "claims_authenticated": self.claims_authenticated,
        }


class LinkedInSessionStore:
    """Persists Playwright storage state outside Git (user-controlled path)."""

    def __init__(self, storage_state_path: str) -> None:
        self._path = Path(storage_state_path)

    @property
    def path(self) -> Path:
        return self._path

    def ensure_parent(self) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        try:
            os.chmod(self._path.parent, 0o700)
        except OSError:
            logger.warning("Could not chmod session directory")

    def exists(self) -> bool:
        return self._path.is_file()

    def delete(self) -> bool:
        if not self._path.exists():
            return False
        self._path.unlink()
        logger.info("LinkedIn session state removed")
        return True

    def status(self, *, online_verified: bool = False) -> LinkedInSessionStatus:
        report = inspect_offline_storage_state(self._path)
        claims = (
            report.quality == OfflineSessionQuality.LIKELY_AUTHENTICATED and online_verified
        )
        msg = report.message
        if report.exists and not online_verified:
            msg += " (offline only — cookie count does not prove live access)"
        if online_verified and report.quality != OfflineSessionQuality.LIKELY_AUTHENTICATED:
            msg = "Online check completed but offline file quality is insufficient."
            claims = False
        return LinkedInSessionStatus(
            exists=report.exists,
            path=report.path,
            readable=report.readable,
            cookie_count=report.cookie_count,
            updated_at=report.updated_at,
            message=msg,
            offline_quality=report.quality.value,
            has_li_at=report.has_li_at,
            online_verified=online_verified,
            claims_authenticated=claims,
        )

    def require_session(self) -> Path:
        report = inspect_offline_storage_state(self._path)
        if not report.exists or not report.readable:
            raise LinkedInCollectionError(
                LinkedInFailureState.AUTHENTICATION_REQUIRED,
                "LinkedIn authentication required (no valid storage state).",
            )
        if report.quality in {OfflineSessionQuality.EMPTY, OfflineSessionQuality.CORRUPT}:
            raise LinkedInCollectionError(
                LinkedInFailureState.SESSION_EXPIRED,
                "LinkedIn session file empty or corrupt.",
            )
        if report.quality == OfflineSessionQuality.UNLIKELY_AUTHENTICATED:
            raise LinkedInCollectionError(
                LinkedInFailureState.AUTHENTICATION_REQUIRED,
                "LinkedIn session missing auth cookies (login likely incomplete).",
            )
        return self._path
import json
import logging
import os
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from app.modules.collection.linkedin.errors import LinkedInCollectionError, LinkedInFailureState

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class LinkedInSessionStatus:
    exists: bool
    path: str
    readable: bool
    cookie_count: int
    updated_at: datetime | None
    message: str


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

    def status(self) -> LinkedInSessionStatus:
        if not self._path.exists():
            return LinkedInSessionStatus(
                exists=False,
                path=str(self._path),
                readable=False,
                cookie_count=0,
                updated_at=None,
                message="No stored session. Manual login required.",
            )
        try:
            raw = self._path.read_text(encoding="utf-8")
            payload: dict[str, Any] = json.loads(raw)
            cookies = payload.get("cookies", [])
            mtime = datetime.fromtimestamp(self._path.stat().st_mtime, tz=UTC)
            return LinkedInSessionStatus(
                exists=True,
                path=str(self._path),
                readable=True,
                cookie_count=len(cookies),
                updated_at=mtime,
                message="Stored session present.",
            )
        except (OSError, json.JSONDecodeError):
            return LinkedInSessionStatus(
                exists=True,
                path=str(self._path),
                readable=False,
                cookie_count=0,
                updated_at=None,
                message="Session file unreadable or corrupt.",
            )

    def require_session(self) -> Path:
        status = self.status()
        if not status.exists or not status.readable:
            raise LinkedInCollectionError(
                LinkedInFailureState.AUTHENTICATION_REQUIRED,
                "LinkedIn authentication required (no valid storage state).",
            )
        if status.cookie_count == 0:
            raise LinkedInCollectionError(
                LinkedInFailureState.SESSION_EXPIRED,
                "LinkedIn session appears empty.",
            )
        return self._path

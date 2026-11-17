"""Prevent overlapping promotion/sync apply (POSIX host lock)."""

from __future__ import annotations

import os
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

DEFAULT_LOCK_PATH = Path("evidence/promotion_backups/.promotion_sync.lock")


@contextmanager
def promotion_sync_lock(
    path: Path | None = None,
    *,
    blocking: bool = False,
) -> Iterator[None]:
    """Raise BlockingIOError if another sync apply holds the lock."""
    lock_path = path or DEFAULT_LOCK_PATH
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    with open(lock_path, "a+", encoding="utf-8") as handle:
        try:
            if blocking:
                os.flock(handle.fileno(), os.LOCK_EX)
            else:
                os.flock(handle.fileno(), os.LOCK_EX | os.LOCK_NB)
        except OSError as exc:
            raise BlockingIOError(
                "Another promotion sync is in progress; refused overlapping apply"
            ) from exc
        handle.write(f"pid={os.getpid()}\n")
        handle.flush()
        try:
            yield
        finally:
            os.flock(handle.fileno(), os.LOCK_UN)
"""Prevent overlapping promotion/sync apply (POSIX host lock)."""

from __future__ import annotations

import fcntl
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
        flag = fcntl.LOCK_EX if blocking else (fcntl.LOCK_EX | fcntl.LOCK_NB)
        try:
            fcntl.flock(handle.fileno(), flag)
        except OSError as exc:
            raise BlockingIOError(
                "Another promotion sync is in progress; refused overlapping apply"
            ) from exc
        handle.write(f"pid={os.getpid()}\n")
        handle.flush()
        try:
            yield
        finally:
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
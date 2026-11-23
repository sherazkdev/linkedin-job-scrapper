"""IANA timezone and digest clock validation."""

from __future__ import annotations

from datetime import time
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError


def validate_iana_timezone(name: str) -> str:
    trimmed = name.strip()
    if not trimmed:
        raise ValueError("digest_timezone is required")
    try:
        ZoneInfo(trimmed)
    except ZoneInfoNotFoundError as exc:
        raise ValueError(f"unknown timezone: {trimmed}") from exc
    return trimmed


def validate_digest_local_time(value: str) -> str:
    parts = value.strip().split(":")
    if len(parts) != 2:
        raise ValueError("digest_local_time must be HH:MM")
    hour, minute = int(parts[0]), int(parts[1])
    time(hour=hour, minute=minute)
    return f"{hour:02d}:{minute:02d}"
"""Offline and post-login validation for Playwright storage state (no secret output)."""

from __future__ import annotations

import json
import shutil
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path
from typing import Any

from app.modules.collection.linkedin.errors import LinkedInFailureState
from app.modules.collection.linkedin.parser import detect_page_state

LOGIN_COOKIE_NAMES = frozenset({"li_at", "liap", "JSESSIONID"})
FEED_PROBE_URL = "https://www.linkedin.com/feed/"
AUTH_WALL_HOST_MARKERS = ("authwall", "checkpoint/lg", "uas/login")
AUTHENTICATED_URL_MARKERS = ("/feed/", "/mynetwork", "/jobs/", "www.linkedin.com/feed")


class LoginOutcome(StrEnum):
    LOGIN_SUCCESS = "LOGIN_SUCCESS"
    LOGIN_INCOMPLETE = "LOGIN_INCOMPLETE"
    VERIFICATION_REQUIRED = "VERIFICATION_REQUIRED"
    AUTHENTICATION_FAILED = "AUTHENTICATION_FAILED"
    ACCOUNT_RESTRICTED = "ACCOUNT_RESTRICTED"
    NETWORK_ERROR = "NETWORK_ERROR"


class OfflineSessionQuality(StrEnum):
    MISSING = "missing"
    CORRUPT = "corrupt"
    EMPTY = "empty"
    UNLIKELY_AUTHENTICATED = "unlikely_authenticated"
    LIKELY_AUTHENTICATED = "likely_authenticated"


@dataclass(slots=True)
class OfflineSessionReport:
    path: str
    exists: bool
    readable: bool
    cookie_count: int
    has_li_at: bool
    has_session_cookie: bool
    quality: OfflineSessionQuality
    updated_at: datetime | None
    message: str


def inspect_offline_storage_state(path: Path) -> OfflineSessionReport:
    if not path.exists():
        return OfflineSessionReport(
            path=str(path),
            exists=False,
            readable=False,
            cookie_count=0,
            has_li_at=False,
            has_session_cookie=False,
            quality=OfflineSessionQuality.MISSING,
            updated_at=None,
            message="No storage state file.",
        )
    try:
        raw = path.read_text(encoding="utf-8")
        payload: dict[str, Any] = json.loads(raw)
        cookies = payload.get("cookies") or []
        if not isinstance(cookies, list):
            raise ValueError("cookies not a list")
        names = {str(c.get("name") or "") for c in cookies if isinstance(c, dict)}
        has_li_at = "li_at" in names
        has_sess = bool(names & LOGIN_COOKIE_NAMES)
        mtime = datetime.fromtimestamp(path.stat().st_mtime, tz=UTC)
        quality = OfflineSessionQuality.LIKELY_AUTHENTICATED
        msg = "Offline file structure OK; online acceptance not verified."
        if len(cookies) == 0:
            quality = OfflineSessionQuality.EMPTY
            msg = "Storage state has zero cookies — not authenticated."
        elif not has_li_at and not has_sess:
            quality = OfflineSessionQuality.UNLIKELY_AUTHENTICATED
            msg = "Missing typical LinkedIn auth cookie names — login may be incomplete."
        return OfflineSessionReport(
            path=str(path),
            exists=True,
            readable=True,
            cookie_count=len(cookies),
            has_li_at=has_li_at,
            has_session_cookie=has_sess,
            quality=quality,
            updated_at=mtime,
            message=msg,
        )
    except (OSError, json.JSONDecodeError, ValueError) as exc:
        return OfflineSessionReport(
            path=str(path),
            exists=True,
            readable=False,
            cookie_count=0,
            has_li_at=False,
            has_session_cookie=False,
            quality=OfflineSessionQuality.CORRUPT,
            updated_at=None,
            message=f"Unreadable storage state: {exc.__class__.__name__}",
        )


def classify_live_page(*, url: str, html: str) -> LoginOutcome:
    lower_url = url.lower()
    lowered = html.lower()
    if "checkpoint" in lower_url or "challenge" in lower_url:
        return LoginOutcome.VERIFICATION_REQUIRED
    if "/login" in lower_url:
        return LoginOutcome.LOGIN_INCOMPLETE
    if any(m in lower_url for m in AUTH_WALL_HOST_MARKERS):
        return LoginOutcome.AUTHENTICATION_FAILED
    page_state = detect_page_state(html)
    if page_state == LinkedInFailureState.VERIFICATION_REQUIRED:
        return LoginOutcome.VERIFICATION_REQUIRED
    if page_state == LinkedInFailureState.AUTHENTICATION_REQUIRED:
        if "/login" in lower_url or 'id="username"' in lowered:
            return LoginOutcome.LOGIN_INCOMPLETE
        return LoginOutcome.AUTHENTICATION_FAILED
    if page_state == LinkedInFailureState.SESSION_EXPIRED:
        return LoginOutcome.AUTHENTICATION_FAILED
    if page_state == LinkedInFailureState.RATE_LIMITED:
        return LoginOutcome.ACCOUNT_RESTRICTED
    if page_state == LinkedInFailureState.ACCESS_DENIED:
        return LoginOutcome.ACCOUNT_RESTRICTED
    if any(m in lower_url for m in AUTHENTICATED_URL_MARKERS):
        return LoginOutcome.LOGIN_SUCCESS
    if "global-nav" in lowered and "feed" in lowered:
        return LoginOutcome.LOGIN_SUCCESS
    if _html_looks_like_job_search(lowered):
        return LoginOutcome.LOGIN_SUCCESS
    return LoginOutcome.LOGIN_INCOMPLETE


def _html_looks_like_job_search(lowered: str) -> bool:
    return "/jobs/view/" in lowered and "jobs-search" in lowered


def outcome_from_failure_state(state: LinkedInFailureState | None) -> LoginOutcome | None:
    if state is None:
        return None
    mapping = {
        LinkedInFailureState.VERIFICATION_REQUIRED: LoginOutcome.VERIFICATION_REQUIRED,
        LinkedInFailureState.AUTHENTICATION_REQUIRED: LoginOutcome.AUTHENTICATION_FAILED,
        LinkedInFailureState.SESSION_EXPIRED: LoginOutcome.AUTHENTICATION_FAILED,
        LinkedInFailureState.ACCESS_DENIED: LoginOutcome.ACCOUNT_RESTRICTED,
        LinkedInFailureState.RATE_LIMITED: LoginOutcome.ACCOUNT_RESTRICTED,
    }
    return mapping.get(state)


def atomic_save_storage_state(
    *,
    source_path: Path,
    destination: Path,
    backup: bool = True,
) -> Path:
    """Replace destination only when source validates as readable JSON with cookies."""
    report = inspect_offline_storage_state(source_path)
    if report.quality not in {
        OfflineSessionQuality.LIKELY_AUTHENTICATED,
        OfflineSessionQuality.UNLIKELY_AUTHENTICATED,
    }:
        raise ValueError(f"Refusing to install session: quality={report.quality.value}")
    if report.cookie_count == 0:
        raise ValueError("Refusing to install empty session")
    destination.parent.mkdir(parents=True, exist_ok=True)
    if backup and destination.exists():
        stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
        backup_path = destination.with_suffix(f".bak.{stamp}.json")
        shutil.copy2(destination, backup_path)
    tmp = destination.with_suffix(f".tmp.{int(time.time())}.json")
    shutil.copy2(source_path, tmp)
    tmp.replace(destination)
    try:
        destination.chmod(0o600)
    except OSError:
        pass
    write_session_epoch_marker(destination.parent)
    return destination


def write_session_epoch_marker(directory: Path) -> Path:
    """Record when the operator refreshed credentials (observer auth-fail window)."""
    directory.mkdir(parents=True, exist_ok=True)
    marker = directory / "session_epoch_at.json"
    payload = {"session_epoch_at": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")}
    marker.write_text(json.dumps(payload) + "\n", encoding="utf-8")
    try:
        marker.chmod(0o600)
    except OSError:
        pass
    return marker


def verify_online_feed_access(*, storage_state_path: Path) -> LoginOutcome:
    """One-shot live check; operator must opt in explicitly (no retry loop)."""
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        return LoginOutcome.NETWORK_ERROR
    try:
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=True)
            try:
                context = browser.new_context(storage_state=str(storage_state_path))
            except Exception:
                browser.close()
                return LoginOutcome.AUTHENTICATION_FAILED
            page = context.new_page()
            try:
                page.goto(FEED_PROBE_URL, wait_until="domcontentloaded", timeout=45_000)
            except Exception:
                browser.close()
                return LoginOutcome.NETWORK_ERROR
            outcome = classify_live_page(url=page.url or "", html=page.content())
            browser.close()
            return outcome
    except Exception:
        return LoginOutcome.NETWORK_ERROR
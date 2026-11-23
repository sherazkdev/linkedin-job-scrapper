"""Operational failure taxonomy for collection runs and alerts."""

from __future__ import annotations

import re
from enum import StrEnum

from app.modules.collection.linkedin.errors import LinkedInFailureState


class CollectionFailureKind(StrEnum):
    TRANSIENT_NETWORK = "transient_network"
    NAVIGATION_TIMEOUT = "navigation_timeout"
    PARSER_OR_LAYOUT = "parser_or_layout"
    WORKER_CRASH = "worker_crash"
    CELERY_BEAT = "celery_beat"
    REDIS_MONGODB = "redis_mongodb"
    AUTH_REQUIRED = "auth_required"
    VERIFICATION_REQUIRED = "verification_required"
    ACCESS_RESTRICTED = "access_restricted"
    DAILY_CAP = "daily_cap"
    VALIDATION = "validation"
    UNKNOWN = "unknown"


_LINKEDIN_STATE_MAP: dict[LinkedInFailureState, CollectionFailureKind] = {
    LinkedInFailureState.AUTHENTICATION_REQUIRED: CollectionFailureKind.AUTH_REQUIRED,
    LinkedInFailureState.SESSION_EXPIRED: CollectionFailureKind.AUTH_REQUIRED,
    LinkedInFailureState.VERIFICATION_REQUIRED: CollectionFailureKind.VERIFICATION_REQUIRED,
    LinkedInFailureState.ACCESS_DENIED: CollectionFailureKind.ACCESS_RESTRICTED,
    LinkedInFailureState.RATE_LIMITED: CollectionFailureKind.ACCESS_RESTRICTED,
    LinkedInFailureState.UNSUPPORTED_PAGE_STRUCTURE: CollectionFailureKind.PARSER_OR_LAYOUT,
    LinkedInFailureState.NAVIGATION_TIMEOUT: CollectionFailureKind.NAVIGATION_TIMEOUT,
    LinkedInFailureState.PAGE_UNRESPONSIVE: CollectionFailureKind.NAVIGATION_TIMEOUT,
    LinkedInFailureState.JS_PROBE_TIMEOUT: CollectionFailureKind.NAVIGATION_TIMEOUT,
    LinkedInFailureState.NO_RESULTS: CollectionFailureKind.UNKNOWN,
}


def classify_error_summary(error_summary: str | None) -> CollectionFailureKind:
    if not error_summary or not str(error_summary).strip():
        return CollectionFailureKind.UNKNOWN
    text = str(error_summary).strip().lower()
    if "daily_cap" in text or "cap_reached" in text:
        return CollectionFailureKind.DAILY_CAP
    if text.startswith("linkedin:"):
        slug = text.split(":", 1)[1].strip()
        try:
            state = LinkedInFailureState(slug.split()[0])
        except ValueError:
            state = None
        if state is not None:
            return _LINKEDIN_STATE_MAP.get(state, CollectionFailureKind.UNKNOWN)
    if any(k in text for k in ("authentication", "session_expired", "auth_required")):
        return CollectionFailureKind.AUTH_REQUIRED
    if "verification" in text or "captcha" in text:
        return CollectionFailureKind.VERIFICATION_REQUIRED
    if "rate_limit" in text or "access_denied" in text:
        return CollectionFailureKind.ACCESS_RESTRICTED
    if "timeout" in text or "navigation" in text:
        return CollectionFailureKind.NAVIGATION_TIMEOUT
    if "unsupported_page" in text or "layout" in text or "parser" in text:
        return CollectionFailureKind.PARSER_OR_LAYOUT
    if "mongo" in text or "redis" in text or "connection refused" in text:
        return CollectionFailureKind.REDIS_MONGODB
    if "validation" in text:
        return CollectionFailureKind.VALIDATION
    if "playwright" in text and "timeout" in text:
        return CollectionFailureKind.NAVIGATION_TIMEOUT
    if re.search(r"\bconnection\b", text):
        return CollectionFailureKind.TRANSIENT_NETWORK
    return CollectionFailureKind.UNKNOWN


def is_auth_or_verification(kind: CollectionFailureKind) -> bool:
    return kind in {
        CollectionFailureKind.AUTH_REQUIRED,
        CollectionFailureKind.VERIFICATION_REQUIRED,
    }
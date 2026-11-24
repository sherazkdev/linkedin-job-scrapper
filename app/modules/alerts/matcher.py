"""Match jobs to saved searches using the same rules as the public jobs API."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from app.modules.alerts.service import job_eligible_for_alert
from app.modules.jobs.models.job import EmploymentType, JobSource, JobStatus, WorkplaceType
from app.modules.jobs.public_visibility import is_publicly_listable


def _ci_eq(left: str | None, right: str | None) -> bool:
    if not right or not right.strip():
        return True
    if not left or not str(left).strip():
        return False
    return str(left).strip().lower() == right.strip().lower()


def job_matches_saved_search(
    job: dict[str, Any],
    search: dict[str, Any],
    *,
    max_age_days: int = 7,
) -> bool:
    """Evaluate a single job document against saved search criteria."""
    if not search.get("enabled", True):
        return False
    if not search.get("alerts_enabled", True):
        return False
    if str(job.get("status") or "") != JobStatus.ACTIVE.value:
        return False
    if not is_publicly_listable(job, max_age_days=max_age_days):
        return False

    if search.get("country_code"):
        cc = str(search["country_code"]).upper()
        if job.get("country_code") != cc and job.get("search_country_code") != cc:
            return False

    if search.get("city"):
        if not _ci_eq(job.get("city"), str(search["city"])):
            return False

    if search.get("employment_type"):
        if job.get("employment_type") != str(search["employment_type"]):
            return False

    remote_pref = search.get("is_remote")
    if remote_pref is True:
        is_remote = job.get("is_remote") is True or job.get("workplace_type") == WorkplaceType.REMOTE.value
        if not is_remote:
            return False
    elif remote_pref is False:
        if job.get("is_remote") is True:
            return False

    q = search.get("q")
    if q and str(q).strip():
        ql = str(q).strip().lower()
        title = str(job.get("title") or "").lower()
        company = str(job.get("company") or "").lower()
        if ql not in title and ql not in company:
            return False

    return True


def event_key_for_outcome(
    *,
    created: bool,
    updated: bool,
    reactivated: bool,
    job: dict[str, Any] | None = None,
) -> str | None:
    """
    Event identity policy:
    - CREATED → `new_job` (once per job per subscriber)
    - UPDATED → `job_updated:<revision_fp>` (once per meaningful content revision)
    - REACTIVATED → `reactivated` (once per job per subscriber; new revision may follow)
    - UNCHANGED → no event
    """
    from app.modules.alerts.constants import (
        EVENT_JOB_UPDATED,
        EVENT_NEW_JOB,
        EVENT_REACTIVATED,
    )
    from app.modules.alerts.revision import alert_revision_fingerprint

    if created:
        return EVENT_NEW_JOB
    if reactivated:
        return EVENT_REACTIVATED
    if updated:
        if job is None:
            return EVENT_JOB_UPDATED
        return f"{EVENT_JOB_UPDATED}:{alert_revision_fingerprint(job)}"
    return None
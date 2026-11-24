"""Stable fingerprints for meaningful job revisions (alert deduplication)."""

from __future__ import annotations

import hashlib
import json
from typing import Any

# Mirrors job_repository._COMPARE_FIELDS — alert updates fire on these changes only.
_REVISION_FIELDS = (
    "title",
    "company",
    "search_country_code",
    "country_code",
    "location_text",
    "city",
    "region",
    "is_remote",
    "description",
    "employment_type",
    "workplace_type",
    "job_url",
    "posted_at",
    "source_posting_label",
    "source_updated_at",
    "description_provided",
)


def alert_revision_fingerprint(job: dict[str, Any]) -> str:
    payload = {k: job.get(k) for k in _REVISION_FIELDS}
    blob = json.dumps(payload, sort_keys=True, default=str, separators=(",", ":"))
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()[:20]
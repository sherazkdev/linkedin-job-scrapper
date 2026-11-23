"""LinkedIn search checkpoint policy (recency-first independent runs).

Independent scheduled or CLI runs always open SERP at offset 0 (newest results).
Pagination to page 1, 2, ... happens only inside a single adapter fetch loop.
Persisted ``page_index`` is never advanced across runs (stale offsets caused
missed results when a previous run stopped on page 8).

``processed_ids`` may still be carried forward for within-target deduplication
unless the operator passes ``--ignore-checkpoint``.
"""

from __future__ import annotations

from typing import Any

_MAX_PROCESSED_IDS = 2000


def prepare_linkedin_run_checkpoint(
    stored: dict[str, Any] | None,
    *,
    ignore_stored: bool,
) -> dict[str, Any] | None:
    """Build adapter input checkpoint for a new collection run."""
    if ignore_stored:
        return None
    if not stored:
        return None
    processed = stored.get("processed_ids") or []
    if not isinstance(processed, list):
        processed = []
    trimmed = [str(x) for x in processed if x][-_MAX_PROCESSED_IDS:]
    out: dict[str, Any] = {
        "page_index": 0,
        "processed_ids": trimmed,
    }
    if kw := stored.get("keyword"):
        out["keyword"] = str(kw)
    return out


def persist_linkedin_run_checkpoint(adapter_checkpoint: dict[str, Any]) -> dict[str, Any]:
    """Normalize checkpoint before writing to Mongo after a completed fetch."""
    processed = adapter_checkpoint.get("processed_ids") or []
    if not isinstance(processed, list):
        processed = []
    trimmed = [str(x) for x in processed if x][-_MAX_PROCESSED_IDS:]
    persisted: dict[str, Any] = {
        "page_index": 0,
        "processed_ids": trimmed,
    }
    if kw := adapter_checkpoint.get("keyword"):
        persisted["keyword"] = str(kw)
    return persisted
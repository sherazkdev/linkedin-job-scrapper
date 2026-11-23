"""LinkedIn search checkpoint policy (recency-first independent runs).

Independent scheduled or CLI runs always open SERP at offset 0 (newest results).
Pagination to page 1, 2, ... happens only inside a single adapter fetch loop.
Persisted ``page_index`` is never advanced across runs (stale offsets caused
missed results when a previous run stopped on page 8).

``processed_ids`` are scoped to a single adapter fetch (in-memory only). They are
**not** reloaded from Mongo on a new run — canonical deduplication is
``(source, sourceJobId)`` at persistence. Reloading SERP skip ids would block
``last_seen_at`` refresh and reactivation for jobs still on page 0.
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
    if ignore_stored or not stored:
        return None
    # Fresh SERP at offset 0; never reuse stored processed_ids across runs.
    out: dict[str, Any] = {"page_index": 0, "processed_ids": []}
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
        # Audit slice only; not used to skip SERP cards on the next run.
        "processed_ids_last_run": trimmed[-50:],
        "processed_ids_last_run_count": len(trimmed),
    }
    if kw := adapter_checkpoint.get("keyword"):
        persisted["keyword"] = str(kw)
    return persisted
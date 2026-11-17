"""Reorder eligible targets for geographic spread without changing eligibility rules."""

from __future__ import annotations

from collections import defaultdict
from datetime import UTC, datetime
from typing import Any


def _sort_key(doc: dict[str, Any]) -> tuple[Any, ...]:
    next_eligible = doc.get("next_eligible_at")
    if not isinstance(next_eligible, datetime):
        next_eligible = datetime.min.replace(tzinfo=UTC)
    last_success = doc.get("last_success_at")
    if not isinstance(last_success, datetime):
        last_success = datetime.min.replace(tzinfo=UTC)
    priority = int(doc.get("priority") or 0)
    return (-priority, next_eligible, last_success, doc.get("keyword") or "")


def fair_country_round_robin(targets: list[dict[str, Any]], *, limit: int) -> list[dict[str, Any]]:
    """Pick up to ``limit`` targets so each country appears at most once before repeats."""
    if limit <= 0 or not targets:
        return []
    by_country: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for doc in targets:
        country = str(doc.get("country_code") or "??").upper()
        by_country[country].append(doc)
    for country in by_country:
        by_country[country].sort(key=_sort_key)

    ordered: list[dict[str, Any]] = []
    countries = sorted(by_country.keys())
    while len(ordered) < limit:
        progressed = False
        for country in countries:
            bucket = by_country[country]
            if not bucket:
                continue
            ordered.append(bucket.pop(0))
            progressed = True
            if len(ordered) >= limit:
                break
        if not progressed:
            break
    return ordered
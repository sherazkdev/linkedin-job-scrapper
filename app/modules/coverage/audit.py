from typing import Any

from pymongo.asynchronous.database import AsyncDatabase

from app.database.collection_indexes import COLLECTION_TARGETS
from app.modules.coverage.manifest import iter_canonical_targets, load_manifest, target_id


def _normalize_keyword(keyword: str) -> str:
    return keyword.strip().lower()


async def audit_manifest_against_scheduler(database: AsyncDatabase[Any]) -> dict[str, Any]:
    """Read-only compare canonical manifest pairs vs collection_targets rows."""
    data = load_manifest()
    canonical_rows = iter_canonical_targets(data)
    canonical_pairs = {
        (r["country_code"], _normalize_keyword(r["keyword_display"]))
        for r in canonical_rows
    }
    canonical_countries = {cc for cc, _ in canonical_pairs}
    canonical_keywords = {kw for _, kw in canonical_pairs}

    sched = database[COLLECTION_TARGETS]
    sched_docs = await sched.find({}).to_list(length=10_000)
    sched_pairs: set[tuple[str, str, str]] = set()
    enabled_by_source: dict[str, int] = {}
    disabled_by_source: dict[str, int] = {}
    for doc in sched_docs:
        source = str(doc.get("source", "unknown"))
        cc = str(doc.get("country_code", "")).upper()
        kw = _normalize_keyword(str(doc.get("keyword", "")))
        sched_pairs.add((source, cc, kw))
        if doc.get("enabled") is True:
            enabled_by_source[source] = enabled_by_source.get(source, 0) + 1
        else:
            disabled_by_source[source] = disabled_by_source.get(source, 0) + 1

    sched_country_keyword = {(cc, kw) for _, cc, kw in sched_pairs}
    missing_in_scheduler = sorted(
        [
            {
                "target_id": target_id(cc, kw),
                "country_code": cc,
                "keyword": kw,
            }
            for cc, kw in canonical_pairs - sched_country_keyword
        ],
        key=lambda r: (r["country_code"], r["keyword"]),
    )

    extra_in_scheduler = sorted(
        [
            {"source": source, "country_code": cc, "keyword": kw}
            for source, cc, kw in sched_pairs
            if (cc, kw) not in canonical_pairs
        ],
        key=lambda r: (r["source"], r["country_code"], r["keyword"]),
    )

    sched_countries = {cc for _, cc, _ in sched_pairs}
    sched_keywords = {kw for _, _, kw in sched_pairs}

    return {
        "manifest_pairs": len(canonical_pairs),
        "manifest_countries": len(canonical_countries),
        "manifest_keywords": len(canonical_keywords),
        "collection_targets_rows": len(sched_docs),
        "collection_targets_distinct_country_keyword": len(sched_country_keyword),
        "collection_targets_countries": sorted(sched_countries),
        "collection_targets_keywords_count": len(sched_keywords),
        "enabled_by_source": enabled_by_source,
        "disabled_by_source": disabled_by_source,
        "missing_canonical_pairs_in_scheduler": len(missing_in_scheduler),
        "missing_sample": missing_in_scheduler[:25],
        "extra_scheduler_pairs_not_in_manifest": len(extra_in_scheduler),
        "extra_sample": extra_in_scheduler[:25],
    }
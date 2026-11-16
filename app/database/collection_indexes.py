import logging
from typing import Any

from pymongo.asynchronous.database import AsyncDatabase

logger = logging.getLogger(__name__)

COLLECTION_TARGETS = "collection_targets"
COLLECTION_RUNS = "collection_runs"
COLLECTION_CHECKPOINTS = "collection_checkpoints"
COVERAGE_TARGETS = "coverage_targets"


_TARGET_KEY_FIELDS = [
    ("source", 1),
    ("country_code", 1),
    ("keyword", 1),
    ("search_location", 1),
]


async def _ensure_target_key_index(
    targets: Any,
    *,
    migrate_search_location: bool,
) -> None:
    """Optional migration: unique key includes search_location (empty = country-wide)."""
    legacy_fields = [("source", 1), ("country_code", 1), ("keyword", 1)]
    index_info = await targets.index_information()
    existing = index_info.get("uniq_target_source_country_keyword")
    if existing is not None:
        key_fields = [field for field, _ in existing["key"]]
        if migrate_search_location:
            if key_fields == [f[0] for f in _TARGET_KEY_FIELDS]:
                return
            await targets.drop_index("uniq_target_source_country_keyword")
        else:
            # Already on 4-field index (e.g. test DB); never downgrade without approval.
            if "search_location" in key_fields:
                return
            if key_fields == [f[0] for f in legacy_fields]:
                return
    if migrate_search_location:
        await targets.update_many(
            {"search_location": {"$exists": False}},
            {"$set": {"search_location": ""}},
        )
        await targets.create_index(
            _TARGET_KEY_FIELDS,
            unique=True,
            name="uniq_target_source_country_keyword",
        )
        return
    if "uniq_target_source_country_keyword" not in (await targets.index_information()):
        await targets.create_index(
            legacy_fields,
            unique=True,
            name="uniq_target_source_country_keyword",
        )


async def ensure_collection_indexes(
    database: AsyncDatabase[Any],
    *,
    migrate_target_search_location: bool = False,
) -> None:
    targets = database[COLLECTION_TARGETS]
    await _ensure_target_key_index(
        targets, migrate_search_location=migrate_target_search_location
    )
    await targets.create_index(
        [("enabled", 1), ("priority", -1), ("next_eligible_at", 1)],
        name="idx_target_schedule",
    )

    runs = database[COLLECTION_RUNS]
    await runs.create_index([("run_id", 1)], unique=True, name="uniq_run_id")
    await runs.create_index(
        [("source", 1), ("country_code", 1), ("started_at", -1)],
        name="idx_run_source_country",
    )
    await runs.create_index([("status", 1), ("started_at", -1)], name="idx_run_status")

    checkpoints = database[COLLECTION_CHECKPOINTS]
    await _ensure_checkpoint_key_index(checkpoints)
    await ensure_coverage_indexes(database)
    logger.info("MongoDB collection-engine indexes ensured")


_CHECKPOINT_KEY_FIELDS = [
    ("source", 1),
    ("country_code", 1),
    ("keyword", 1),
    ("search_location", 1),
]


async def _ensure_checkpoint_key_index(checkpoints: Any) -> None:
    """Unique checkpoint key includes search_location (empty string = country-wide)."""
    index_info = await checkpoints.index_information()
    existing = index_info.get("uniq_checkpoint_key")
    if existing is not None:
        key_fields = [field for field, _ in existing["key"]]
        if key_fields == [f[0] for f in _CHECKPOINT_KEY_FIELDS]:
            return
        await checkpoints.drop_index("uniq_checkpoint_key")
    await checkpoints.update_many(
        {"search_location": {"$exists": False}},
        {"$set": {"search_location": ""}},
    )
    await checkpoints.create_index(
        _CHECKPOINT_KEY_FIELDS,
        unique=True,
        name="uniq_checkpoint_key",
    )


async def ensure_coverage_indexes(database: AsyncDatabase[Any]) -> None:
    coverage = database[COVERAGE_TARGETS]
    await coverage.create_index("target_id", unique=True, name="uniq_coverage_target_id")
    await coverage.create_index(
        [("country_code", 1), ("keyword", 1)],
        unique=True,
        name="uniq_coverage_country_keyword",
    )
    await coverage.create_index(
        [("enabled", 1), ("country_code", 1)],
        name="idx_coverage_enabled_country",
    )
    logger.info("MongoDB coverage_targets indexes ensured")

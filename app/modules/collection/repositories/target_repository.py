from datetime import UTC, datetime, timedelta
from typing import Any

from pymongo import ReturnDocument
from pymongo.asynchronous.collection import AsyncCollection
from pymongo.asynchronous.database import AsyncDatabase

from app.database.collection_indexes import COLLECTION_TARGETS
from app.modules.collection.repositories.checkpoint_repository import (
    normalize_search_location_key,
)
from app.modules.jobs.models.job import JobSource


def _target_identity_filter(
    *,
    source: JobSource,
    country_code: str,
    keyword: str,
    search_location: str | None = None,
) -> dict[str, str]:
    return {
        "source": source.value,
        "country_code": country_code.upper(),
        "keyword": keyword.strip().lower(),
        "search_location": normalize_search_location_key(search_location),
    }


def _target_match_query(
    *,
    source: JobSource,
    country_code: str,
    keyword: str,
    search_location: str | None = None,
) -> dict[str, Any]:
    """Mongo filter for a target row (includes legacy docs missing ``search_location``)."""
    loc_key = normalize_search_location_key(search_location)
    base: dict[str, Any] = {
        "source": source.value,
        "country_code": country_code.upper(),
        "keyword": keyword.strip().lower(),
    }
    if loc_key:
        base["search_location"] = loc_key
        return base
    return {
        **base,
        "$or": [
            {"search_location": ""},
            {"search_location": {"$exists": False}},
        ],
    }


def _merge_target_query(match: dict[str, Any], *clauses: dict[str, Any]) -> dict[str, Any]:
    parts: list[dict[str, Any]] = []
    if "$or" in match and "search_location" not in match:
        parts.append({k: match[k] for k in ("source", "country_code", "keyword") if k in match})
        parts.append({"$or": match["$or"]})
    else:
        parts.append(match)
    parts.extend(clauses)
    if len(parts) == 1:
        return parts[0]
    return {"$and": parts}

COUNTRY_NAMES = {
    "DE": "Germany",
    "SE": "Sweden",
    "US": "United States",
    "GB": "United Kingdom",
    "CA": "Canada",
    "PK": "Pakistan",
}


def lock_is_active(target: dict[str, Any] | None, *, now: datetime | None = None) -> bool:
    if target is None:
        return False
    owner = target.get("lock_owner")
    locked_until = target.get("locked_until")
    if not owner or locked_until is None:
        return False
    clock = now or datetime.now(UTC)
    if locked_until.tzinfo is None:
        locked_until = locked_until.replace(tzinfo=UTC)
    return locked_until >= clock


class TargetRepository:
    def __init__(self, database: AsyncDatabase[Any]) -> None:
        self._collection: AsyncCollection[Any] = database[COLLECTION_TARGETS]

    async def ensure_defaults(self) -> int:
        await self._collection.update_many(
            {"search_location": {"$exists": False}},
            {"$set": {"search_location": ""}},
        )
        defaults = [
            ("PK", "software engineer"),
            ("DE", "backend engineer"),
            ("US", "data engineer"),
            ("SE", "platform engineer"),
        ]
        inserted = 0
        for code, keyword in defaults:
            country_name = COUNTRY_NAMES.get(code, code)
            result = await self._collection.update_one(
                _target_match_query(
                    source=JobSource.FIXTURE,
                    country_code=code,
                    keyword=keyword,
                ),
                {
                    "$setOnInsert": {
                        "source": JobSource.FIXTURE.value,
                        "country_code": code,
                        "country_name": country_name,
                        "keyword": keyword,
                        "search_location": "",
                        "enabled": True,
                        "priority": 100,
                        "max_jobs_per_run": 10,
                        "last_success_at": None,
                        "last_failure_at": None,
                        "last_run_at": None,
                        "last_error_summary": None,
                        "next_eligible_at": None,
                        "lock_owner": None,
                        "locked_until": None,
                    }
                },
                upsert=True,
            )
            if result.upserted_id is not None:
                inserted += 1
        return inserted

    async def upsert_target(
        self,
        *,
        source: JobSource,
        country_code: str,
        keyword: str,
        country_name: str | None = None,
        search_location: str | None = None,
        enabled: bool = True,
        priority: int = 100,
        max_jobs_per_run: int = 10,
    ) -> dict[str, Any]:
        code = country_code.upper()
        kw = keyword.strip().lower()
        name = country_name or COUNTRY_NAMES.get(code, code)
        loc_key = normalize_search_location_key(search_location)
        identity = _target_match_query(
            source=source,
            country_code=code,
            keyword=kw,
            search_location=loc_key,
        )
        await self._collection.update_one(
            identity,
            {
                "$set": {
                    "enabled": enabled,
                    "priority": priority,
                    "max_jobs_per_run": max_jobs_per_run,
                },
                "$setOnInsert": {
                    "source": source.value,
                    "country_code": code,
                    "country_name": name,
                    "keyword": kw,
                    "search_location": loc_key,
                    "last_success_at": None,
                    "last_failure_at": None,
                    "last_run_at": None,
                    "last_error_summary": None,
                    "next_eligible_at": None,
                    "lock_owner": None,
                    "locked_until": None,
                },
            },
            upsert=True,
        )
        doc = await self._collection.find_one(
            _target_identity_filter(
                source=source,
                country_code=code,
                keyword=kw,
                search_location=loc_key,
            )
        )
        if doc is None:
            doc = await self._collection.find_one(identity)
        if doc is None:
            raise RuntimeError("Target upsert failed")
        return doc

    async def find_target(
        self,
        *,
        source: JobSource,
        country_code: str,
        keyword: str,
        search_location: str | None = None,
    ) -> dict[str, Any] | None:
        return await self._collection.find_one(
            _target_match_query(
                source=source,
                country_code=country_code,
                keyword=keyword,
                search_location=search_location,
            )
        )

    async def try_acquire_lock(
        self,
        *,
        source: JobSource,
        country_code: str,
        keyword: str,
        owner: str,
        lease_seconds: int,
        search_location: str | None = None,
    ) -> dict[str, Any] | None:
        now = datetime.now(UTC)
        locked_until = now + timedelta(seconds=lease_seconds)
        match = _target_match_query(
            source=source,
            country_code=country_code,
            keyword=keyword,
            search_location=search_location,
        )
        query = _merge_target_query(
            match,
            {"enabled": True},
            {
                "$or": [
                    {"lock_owner": None},
                    {"locked_until": {"$lt": now}},
                    {"lock_owner": owner},
                ]
            },
        )
        updated = await self._collection.find_one_and_update(
            query,
            {"$set": {"lock_owner": owner, "locked_until": locked_until}},
            return_document=ReturnDocument.AFTER,
        )
        if updated is not None and updated.get("search_location") in (None, ""):
            loc_key = normalize_search_location_key(search_location)
            if loc_key == "" and updated.get("search_location") is None:
                await self._collection.update_one(
                    {"_id": updated["_id"]},
                    {"$set": {"search_location": ""}},
                )
                updated["search_location"] = ""
        return updated

    async def release_lock(self, target_id: Any, owner: str) -> None:
        await self._collection.update_one(
            {"_id": target_id, "lock_owner": owner},
            {"$set": {"lock_owner": None, "locked_until": None}},
        )

    async def release_stale_lock(
        self,
        *,
        source: JobSource,
        country_code: str,
        keyword: str,
        search_location: str | None = None,
        now: datetime | None = None,
    ) -> bool:
        clock = now or datetime.now(UTC)
        match = _target_match_query(
            source=source,
            country_code=country_code,
            keyword=keyword,
            search_location=search_location,
        )
        query = _merge_target_query(
            match,
            {"lock_owner": {"$ne": None}},
            {
                "$or": [
                    {"locked_until": {"$lt": clock}},
                    {"locked_until": None},
                ]
            },
        )
        result = await self._collection.update_one(
            query,
            {"$set": {"lock_owner": None, "locked_until": None}},
        )
        return result.modified_count == 1

    async def renew_lock(self, target_id: Any, *, owner: str, lease_seconds: int) -> bool:
        now = datetime.now(UTC)
        result = await self._collection.update_one(
            {
                "_id": target_id,
                "lock_owner": owner,
                "$or": [
                    {"locked_until": {"$gte": now}},
                    {"locked_until": None},
                ],
            },
            {"$set": {"locked_until": now + timedelta(seconds=lease_seconds)}},
        )
        return result.matched_count == 1

    async def list_eligible_targets(
        self,
        *,
        allowed_sources: list[JobSource],
        limit: int = 100,
        now: datetime | None = None,
    ) -> list[dict[str, Any]]:
        if not allowed_sources:
            return []
        clock = now or datetime.now(UTC)
        cursor = (
            self._collection.find(
                {
                    "enabled": True,
                    "source": {"$in": [source.value for source in allowed_sources]},
                    "$and": [
                        {
                            "$or": [
                                {"next_eligible_at": None},
                                {"next_eligible_at": {"$lte": clock}},
                            ]
                        },
                        {
                            "$or": [
                                {"lock_owner": None},
                                {"locked_until": None},
                                {"locked_until": {"$lt": clock}},
                            ]
                        },
                    ],
                }
            )
            .sort([("priority", -1), ("next_eligible_at", 1)])
            .limit(limit)
        )
        return await cursor.to_list(length=limit)

    async def mark_success(
        self,
        target_id: Any,
        *,
        cooldown_seconds: int = 0,
        last_run_stats: dict[str, Any] | None = None,
    ) -> None:
        now = datetime.now(UTC)
        next_eligible = now if cooldown_seconds <= 0 else now + timedelta(seconds=cooldown_seconds)
        payload: dict[str, Any] = {
            "last_success_at": now,
            "last_run_at": now,
            "next_eligible_at": next_eligible,
            "last_error_summary": None,
        }
        if last_run_stats:
            for key in (
                "collected_count",
                "created_count",
                "updated_count",
                "rejected_count",
                "duration_seconds",
                "run_id",
            ):
                if key in last_run_stats and last_run_stats[key] is not None:
                    payload[f"last_run_{key}"] = last_run_stats[key]
        await self._collection.update_one({"_id": target_id}, {"$set": payload})

    async def mark_failure(
        self,
        target_id: Any,
        *,
        error_summary: str | None = None,
        pause_seconds: int = 3600,
        disable_target: bool = False,
        last_run_stats: dict[str, Any] | None = None,
    ) -> None:
        now = datetime.now(UTC)
        next_eligible = now + timedelta(seconds=max(pause_seconds, 0))
        payload: dict[str, Any] = {
            "last_failure_at": now,
            "last_run_at": now,
            "next_eligible_at": next_eligible,
        }
        if last_run_stats:
            if last_run_stats.get("duration_seconds") is not None:
                payload["last_run_duration_seconds"] = last_run_stats["duration_seconds"]
            if last_run_stats.get("run_id"):
                payload["last_run_run_id"] = last_run_stats["run_id"]
        if error_summary:
            payload["last_error_summary"] = error_summary[:500]
        update: dict[str, Any] = {"$set": payload}
        if disable_target:
            update["$set"]["enabled"] = False
        await self._collection.update_one({"_id": target_id}, update)

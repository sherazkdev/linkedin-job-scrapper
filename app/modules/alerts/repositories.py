"""Mongo repositories for alert subscribers, saved searches, and notifications."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from bson import ObjectId
from pymongo.asynchronous.collection import AsyncCollection
from pymongo.asynchronous.database import AsyncDatabase
from pymongo.errors import DuplicateKeyError

from app.modules.alerts.constants import (
    ALERT_DIGEST_STATE,
    ALERT_NOTIFICATIONS,
    ALERT_SUBSCRIBERS,
    SAVED_JOB_SEARCHES,
)


class AlertSubscriberRepository:
    def __init__(self, database: AsyncDatabase[Any]) -> None:
        self._col: AsyncCollection[Any] = database[ALERT_SUBSCRIBERS]

    async def create(self, *, subscriber_id: str, token_hash: str) -> dict[str, Any]:
        doc = {
            "subscriber_id": subscriber_id,
            "token_hash": token_hash,
            "created_at": datetime.now(UTC),
        }
        await self._col.insert_one(doc)
        return doc

    async def find_by_token_hash(self, token_hash: str) -> dict[str, Any] | None:
        return await self._col.find_one({"token_hash": token_hash})


class SavedSearchRepository:
    def __init__(self, database: AsyncDatabase[Any]) -> None:
        self._col: AsyncCollection[Any] = database[SAVED_JOB_SEARCHES]

    async def create(self, *, subscriber_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        now = datetime.now(UTC)
        doc = {
            "_id": ObjectId(),
            "search_id": str(uuid4()),
            "subscriber_id": subscriber_id,
            "q": payload.get("q"),
            "country_code": payload.get("country_code"),
            "city": payload.get("city"),
            "employment_type": (
                payload["employment_type"].value
                if payload.get("employment_type") is not None
                and hasattr(payload["employment_type"], "value")
                else payload.get("employment_type")
            ),
            "is_remote": payload.get("is_remote"),
            "enabled": True,
            "alerts_enabled": payload.get("alerts_enabled", True),
            "digest_enabled": payload.get("digest_enabled", False),
            "digest_local_time": payload.get("digest_local_time"),
            "digest_timezone": payload.get("digest_timezone") or "UTC",
            "digest_max_jobs": int(payload.get("digest_max_jobs") or 10),
            "created_at": now,
            "updated_at": now,
        }
        await self._col.insert_one(doc)
        return doc

    async def list_for_subscriber(self, subscriber_id: str) -> list[dict[str, Any]]:
        cursor = self._col.find({"subscriber_id": subscriber_id}).sort("created_at", -1)
        return await cursor.to_list(length=500)

    async def get_owned(self, *, subscriber_id: str, search_id: str) -> dict[str, Any] | None:
        return await self._col.find_one({"subscriber_id": subscriber_id, "search_id": search_id})

    async def update_owned(
        self,
        *,
        subscriber_id: str,
        search_id: str,
        updates: dict[str, Any],
    ) -> dict[str, Any] | None:
        updates["updated_at"] = datetime.now(UTC)
        return await self._col.find_one_and_update(
            {"subscriber_id": subscriber_id, "search_id": search_id},
            {"$set": updates},
            return_document=True,
        )

    async def delete_owned(self, *, subscriber_id: str, search_id: str) -> bool:
        result = await self._col.delete_one({"subscriber_id": subscriber_id, "search_id": search_id})
        return result.deleted_count > 0

    async def list_alert_enabled(self) -> list[dict[str, Any]]:
        cursor = self._col.find({"enabled": True, "alerts_enabled": True})
        return await cursor.to_list(length=10_000)

    async def list_digest_enabled(self) -> list[dict[str, Any]]:
        cursor = self._col.find(
            {"enabled": True, "digest_enabled": True, "alerts_enabled": True},
        )
        return await cursor.to_list(length=10_000)


class NotificationRepository:
    def __init__(self, database: AsyncDatabase[Any]) -> None:
        self._col: AsyncCollection[Any] = database[ALERT_NOTIFICATIONS]

    async def insert_in_app(
        self,
        *,
        subscriber_id: str,
        job_id: str,
        event_key: str,
        job_snapshot: dict[str, Any],
    ) -> dict[str, Any] | None:
        now = datetime.now(UTC)
        doc = {
            "_id": ObjectId(),
            "subscriber_id": subscriber_id,
            "job_id": job_id,
            "event_key": event_key,
            "title": job_snapshot.get("title"),
            "company": job_snapshot.get("company"),
            "job_url": job_snapshot.get("job_url"),
            "read_at": None,
            "created_at": now,
            "channel": "in_app",
            "payload_type": "in_app",
        }
        try:
            await self._col.insert_one(doc)
            return doc
        except DuplicateKeyError:
            return None

    async def list_for_subscriber(
        self,
        *,
        subscriber_id: str,
        page: int,
        page_size: int,
        unread_only: bool = False,
    ) -> tuple[list[dict[str, Any]], int, int]:
        filt: dict[str, Any] = {"subscriber_id": subscriber_id}
        if unread_only:
            filt["read_at"] = None
        total = await self._col.count_documents(filt)
        unread = await self._col.count_documents({"subscriber_id": subscriber_id, "read_at": None})
        skip = (page - 1) * page_size
        cursor = (
            self._col.find(filt).sort("created_at", -1).skip(skip).limit(page_size)
        )
        items = await cursor.to_list(length=page_size)
        return items, total, unread

    async def mark_read(
        self,
        *,
        subscriber_id: str,
        notification_ids: list[str] | None,
        mark_all: bool,
    ) -> int:
        now = datetime.now(UTC)
        if mark_all:
            result = await self._col.update_many(
                {"subscriber_id": subscriber_id, "read_at": None},
                {"$set": {"read_at": now}},
            )
            return result.modified_count
        if not notification_ids:
            return 0
        oids = [ObjectId(n) for n in notification_ids if ObjectId.is_valid(n)]
        if not oids:
            return 0
        result = await self._col.update_many(
            {"subscriber_id": subscriber_id, "_id": {"$in": oids}, "read_at": None},
            {"$set": {"read_at": now}},
        )
        return result.modified_count

    async def dismiss(self, *, subscriber_id: str, notification_id: str) -> bool:
        if not ObjectId.is_valid(notification_id):
            return False
        result = await self._col.delete_one(
            {"subscriber_id": subscriber_id, "_id": ObjectId(notification_id)},
        )
        return result.deleted_count > 0


class DigestStateRepository:
    def __init__(self, database: AsyncDatabase[Any]) -> None:
        self._col: AsyncCollection[Any] = database[ALERT_DIGEST_STATE]

    async def get(self, subscriber_id: str) -> dict[str, Any] | None:
        return await self._col.find_one({"subscriber_id": subscriber_id})

    async def upsert_sent(self, *, subscriber_id: str, digest_key: str) -> None:
        now = datetime.now(UTC)
        await self._col.update_one(
            {"subscriber_id": subscriber_id},
            {
                "$set": {
                    "last_digest_key": digest_key,
                    "last_sent_at": now,
                },
                "$setOnInsert": {"subscriber_id": subscriber_id},
            },
            upsert=True,
        )

    async def already_sent(self, *, subscriber_id: str, digest_key: str) -> bool:
        doc = await self.get(subscriber_id)
        if not doc:
            return False
        return str(doc.get("last_digest_key") or "") == digest_key
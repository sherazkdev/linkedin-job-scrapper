from enum import StrEnum


class CollectionRunStatus(StrEnum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class JobUpsertOutcome(StrEnum):
    CREATED = "created"
    UPDATED = "updated"
    UNCHANGED = "unchanged"


class CollectionErrorCategory(StrEnum):
    VALIDATION = "validation"
    ADAPTER = "adapter"
    DATABASE = "database"
    LOCK = "lock"
    CONFIGURATION = "configuration"
    UNKNOWN = "unknown"

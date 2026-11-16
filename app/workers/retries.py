"""Classify worker-level retry eligibility (never retry account restrictions)."""

from pymongo.errors import ConnectionFailure, NetworkTimeout, ServerSelectionTimeoutError

from app.modules.collection.linkedin.errors import LinkedInCollectionError
from app.modules.collection.services.collector import CollectionLockError


def is_transient_worker_failure(exc: BaseException) -> bool:
    if isinstance(exc, CollectionLockError):
        return True
    if isinstance(exc, LinkedInCollectionError):
        return exc.retryable
    if isinstance(exc, ConnectionFailure | NetworkTimeout | ServerSelectionTimeoutError):
        return True
    if isinstance(exc, TimeoutError):
        return True
    name = exc.__class__.__name__.lower()
    return "timeout" in name or "connection" in name

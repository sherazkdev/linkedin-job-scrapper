from app.modules.collection.linkedin.errors import LinkedInCollectionError, LinkedInFailureState
from app.modules.collection.services.collector import CollectionLockError
from app.workers.retries import is_transient_worker_failure


def test_linkedin_security_errors_not_retryable() -> None:
    exc = LinkedInCollectionError(LinkedInFailureState.VERIFICATION_REQUIRED, "challenge")
    assert is_transient_worker_failure(exc) is False


def test_lock_error_is_transient() -> None:
    assert is_transient_worker_failure(CollectionLockError("busy")) is True


def test_timeout_is_transient() -> None:
    assert is_transient_worker_failure(TimeoutError("slow")) is True

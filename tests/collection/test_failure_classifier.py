from app.modules.collection.linkedin.errors import LinkedInFailureState
from app.modules.collection.operations.failure_classifier import (
    CollectionFailureKind,
    classify_error_summary,
)


def test_classify_linkedin_auth() -> None:
    assert (
        classify_error_summary(f"linkedin:{LinkedInFailureState.AUTHENTICATION_REQUIRED.value}")
        == CollectionFailureKind.AUTH_REQUIRED
    )


def test_classify_verification() -> None:
    assert classify_error_summary("linkedin:verification_required") == CollectionFailureKind.VERIFICATION_REQUIRED


def test_classify_daily_cap() -> None:
    assert classify_error_summary("daily_cap_reached") == CollectionFailureKind.DAILY_CAP
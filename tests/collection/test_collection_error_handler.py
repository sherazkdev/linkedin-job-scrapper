from playwright.async_api import Error as PlaywrightError

from app.modules.collection.linkedin.errors import LinkedInCollectionError, LinkedInFailureState
from app.modules.collection.models.enums import CollectionErrorCategory
from app.modules.collection.services.error_handler import CollectionErrorHandler


def test_playwright_error_categorized_as_adapter() -> None:
    exc = PlaywrightError("Target page, context or browser has been closed")
    assert CollectionErrorHandler.categorize(exc) == CollectionErrorCategory.ADAPTER


def test_playwright_error_summary_includes_message() -> None:
    exc = PlaywrightError("net::ERR_ABORTED")
    summary = CollectionErrorHandler().record(exc)
    assert summary.startswith("playwright:")
    assert "ERR_ABORTED" in summary


def test_linkedin_error_summary_uses_state() -> None:
    exc = LinkedInCollectionError(LinkedInFailureState.NO_RESULTS, "empty")
    assert CollectionErrorHandler().record(exc) == "linkedin:no_results"
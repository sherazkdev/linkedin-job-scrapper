from enum import StrEnum


class LinkedInFailureState(StrEnum):
    AUTHENTICATION_REQUIRED = "authentication_required"
    SESSION_EXPIRED = "session_expired"
    VERIFICATION_REQUIRED = "verification_required"
    ACCESS_DENIED = "access_denied"
    RATE_LIMITED = "rate_limited"
    UNSUPPORTED_PAGE_STRUCTURE = "unsupported_page_structure"
    NAVIGATION_TIMEOUT = "navigation_timeout"
    PAGE_UNRESPONSIVE = "page_unresponsive"
    JS_PROBE_TIMEOUT = "js_probe_timeout"
    NO_RESULTS = "no_results"


class LinkedInCollectionError(Exception):
    """Raised when LinkedIn collection cannot proceed safely."""

    def __init__(
        self,
        state: LinkedInFailureState,
        message: str,
        *,
        retryable: bool = False,
    ) -> None:
        self.state = state
        self.retryable = retryable
        super().__init__(message)


NON_RETRYABLE = {
    LinkedInFailureState.AUTHENTICATION_REQUIRED,
    LinkedInFailureState.SESSION_EXPIRED,
    LinkedInFailureState.VERIFICATION_REQUIRED,
    LinkedInFailureState.ACCESS_DENIED,
    LinkedInFailureState.RATE_LIMITED,
    LinkedInFailureState.UNSUPPORTED_PAGE_STRUCTURE,
    LinkedInFailureState.PAGE_UNRESPONSIVE,
    LinkedInFailureState.JS_PROBE_TIMEOUT,
}

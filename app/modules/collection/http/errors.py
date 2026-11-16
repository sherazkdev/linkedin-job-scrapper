from enum import StrEnum


class PublicBoardFailureState(StrEnum):
    DISABLED = "disabled"
    RATE_LIMITED = "rate_limited"
    FORBIDDEN = "forbidden"
    HTTP_ERROR = "http_error"
    INVALID_PAYLOAD = "invalid_payload"
    NOT_FOUND = "not_found"
    TIMEOUT = "timeout"
    RESPONSE_TOO_LARGE = "response_too_large"


class PublicBoardCollectionError(Exception):
    def __init__(
        self,
        state: PublicBoardFailureState,
        message: str,
        *,
        retryable: bool = False,
    ) -> None:
        super().__init__(message)
        self.state = state
        self.retryable = retryable
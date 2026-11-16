import re

from app.modules.collection.http.errors import PublicBoardCollectionError, PublicBoardFailureState

# Public board slug/token (Greenhouse token, Lever site, Ashby job board name).
BOARD_SITE_PATTERN = re.compile(r"^[A-Za-z0-9](?:[A-Za-z0-9._-]{0,62}[A-Za-z0-9])?$")


def validate_board_site(value: str, *, field_name: str = "board_site") -> str:
    token = value.strip()
    if not token or len(token) > 64:
        raise PublicBoardCollectionError(
            PublicBoardFailureState.INVALID_PAYLOAD,
            f"{field_name} must be 1-64 characters",
            retryable=False,
        )
    if not BOARD_SITE_PATTERN.match(token):
        raise PublicBoardCollectionError(
            PublicBoardFailureState.INVALID_PAYLOAD,
            f"{field_name} contains invalid characters",
            retryable=False,
        )
    return token


def scoped_source_job_id(board_site: str, provider_job_id: str) -> str:
    """Disambiguate numeric IDs across different employer boards."""
    board = board_site.strip().lower()
    job_id = provider_job_id.strip()
    if not job_id:
        raise ValueError("provider_job_id is required")
    return f"{board}:{job_id}"
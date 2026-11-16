from urllib.parse import urlparse

APPROVED_PUBLIC_BOARD_HOSTS = frozenset(
    {
        "boards-api.greenhouse.io",
        "api.lever.co",
        "api.eu.lever.co",
        "api.ashbyhq.com",
        "api.adzuna.com",
    }
)

DEFAULT_MAX_RESPONSE_BYTES = 10 * 1024 * 1024


def assert_approved_url(url: str) -> None:
    parsed = urlparse(url)
    if parsed.scheme != "https":
        raise ValueError("Only HTTPS URLs are permitted")
    host = (parsed.hostname or "").lower()
    if host not in APPROVED_PUBLIC_BOARD_HOSTS:
        raise ValueError(f"Host not allowed for public board client: {host}")
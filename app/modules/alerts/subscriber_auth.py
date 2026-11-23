"""Bearer credentials for anonymous alert subscribers (hashed at rest)."""

from __future__ import annotations

import hashlib
import secrets
from uuid import uuid4


def new_subscriber_id() -> str:
    return str(uuid4())


def issue_bearer_token() -> str:
    return secrets.token_urlsafe(32)


def hash_bearer_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def verify_token_format(token: str) -> bool:
    return 16 <= len(token) <= 256
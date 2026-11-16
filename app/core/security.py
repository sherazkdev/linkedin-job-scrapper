import secrets


def verify_internal_token(provided: str | None, expected: str | None) -> bool:
    if not expected or not provided:
        return False
    return secrets.compare_digest(provided, expected)
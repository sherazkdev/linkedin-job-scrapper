from app.modules.alerts.subscriber_auth import hash_bearer_token, issue_bearer_token, verify_token_format


def test_bearer_token_format_and_hash_stable() -> None:
    token = issue_bearer_token()
    assert verify_token_format(token)
    h1 = hash_bearer_token(token)
    h2 = hash_bearer_token(token)
    assert h1 == h2
    assert len(h1) == 64


def test_reject_short_tokens() -> None:
    assert not verify_token_format("short")
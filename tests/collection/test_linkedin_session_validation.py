import json
from pathlib import Path

import pytest

from app.modules.collection.linkedin.session import LinkedInSessionStore
from app.modules.collection.linkedin.session_validation import (
    LoginOutcome,
    OfflineSessionQuality,
    atomic_save_storage_state,
    classify_live_page,
    inspect_offline_storage_state,
    write_session_epoch_marker,
)
from app.modules.collection.linkedin.auth_circuit import (
    CollectionAuthMode,
    auth_fail_query_since,
    decision_from_linkedin_error,
)
from app.modules.collection.linkedin.errors import LinkedInCollectionError, LinkedInFailureState


def _storage_with_li_at(path: Path) -> None:
    payload = {
        "cookies": [
            {"name": "li_at", "value": "redacted", "domain": ".linkedin.com", "path": "/"},
            {"name": "JSESSIONID", "value": "x", "domain": ".linkedin.com", "path": "/"},
        ],
        "origins": [],
    }
    path.write_text(json.dumps(payload), encoding="utf-8")


def test_inspect_missing_file(tmp_path: Path) -> None:
    report = inspect_offline_storage_state(tmp_path / "missing.json")
    assert report.quality == OfflineSessionQuality.MISSING


def test_inspect_unauthenticated_cookie_count_only(tmp_path: Path) -> None:
    path = tmp_path / "storage_state.json"
    path.write_text(json.dumps({"cookies": [{"name": "bcookie", "value": "1"}]}), encoding="utf-8")
    report = inspect_offline_storage_state(path)
    assert report.cookie_count == 1
    assert report.quality == OfflineSessionQuality.UNLIKELY_AUTHENTICATED
    assert not report.has_li_at


def test_classify_login_incomplete_on_login_page() -> None:
    html = '<html><form><input id="username"/></form></html>'
    assert classify_live_page(url="https://www.linkedin.com/login", html=html) == LoginOutcome.LOGIN_INCOMPLETE


def test_classify_verification_checkpoint() -> None:
    html = "<html>checkpoint challenge</html>"
    url = "https://www.linkedin.com/checkpoint/challenge/abc"
    assert classify_live_page(url=url, html=html) == LoginOutcome.VERIFICATION_REQUIRED


def test_classify_login_success_feed() -> None:
    html = '<div class="global-nav">feed</div>'
    assert classify_live_page(url="https://www.linkedin.com/feed/", html=html) == LoginOutcome.LOGIN_SUCCESS


def test_atomic_save_refuses_empty(tmp_path: Path) -> None:
    src = tmp_path / "src.json"
    src.write_text(json.dumps({"cookies": []}), encoding="utf-8")
    dest = tmp_path / "dest.json"
    with pytest.raises(ValueError, match="empty"):
        atomic_save_storage_state(source_path=src, destination=dest, backup=False)


def test_atomic_save_replaces_with_backup(tmp_path: Path) -> None:
    dest = tmp_path / "storage_state.json"
    dest.write_text("old", encoding="utf-8")
    src = tmp_path / "src.json"
    _storage_with_li_at(src)
    atomic_save_storage_state(source_path=src, destination=dest, backup=True)
    assert json.loads(dest.read_text(encoding="utf-8"))["cookies"]
    backups = list(tmp_path.glob("storage_state.bak.*.json"))
    assert len(backups) == 1


def test_session_store_status_never_claims_auth_without_online(tmp_path: Path) -> None:
    path = tmp_path / "storage_state.json"
    _storage_with_li_at(path)
    store = LinkedInSessionStore(str(path))
    status = store.status(online_verified=False)
    assert status.offline_quality == OfflineSessionQuality.LIKELY_AUTHENTICATED.value
    assert status.claims_authenticated is False


def test_session_store_claims_auth_only_when_online_verified(tmp_path: Path) -> None:
    path = tmp_path / "storage_state.json"
    _storage_with_li_at(path)
    store = LinkedInSessionStore(str(path))
    assert store.status(online_verified=True).claims_authenticated is True


def test_auth_circuit_verification_pauses() -> None:
    exc = LinkedInCollectionError(LinkedInFailureState.VERIFICATION_REQUIRED, "challenge")
    decision = decision_from_linkedin_error(exc)
    assert decision.mode == CollectionAuthMode.PAUSED_VERIFICATION
    assert decision.pause_live_requests


def test_auth_circuit_network_not_auth() -> None:
    decision = decision_from_linkedin_error(TimeoutError("navigation"))
    assert decision.mode == CollectionAuthMode.HEALTHY
    assert decision.pause_live_requests is False


def test_session_epoch_marker_and_auth_window(tmp_path: Path) -> None:
    marker = write_session_epoch_marker(tmp_path)
    since = auth_fail_query_since(session_epoch_file=str(marker))
    assert since.tzinfo is not None
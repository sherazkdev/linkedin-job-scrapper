from pathlib import Path

import pytest

_REPO = Path(__file__).resolve().parents[2]
_SMOKE = _REPO / "scripts/server_pilot_software_engineer.sh"
_VERIFY = _REPO / "scripts/server_pilot_api_verify.sh"


@pytest.fixture(scope="module")
def require_ops_scripts() -> None:
    if not _SMOKE.is_file() or not _VERIFY.is_file():
        pytest.skip("Ops scripts not present in pytest image (run on host checkout)")


def test_pilot_software_engineer_reuses_persistent_pilot_api(require_ops_scripts: None) -> None:
    text = _SMOKE.read_text(encoding="utf-8")
    assert "server_pilot_api_up.sh" in text
    assert "linkedin-pilot-api-verify" not in text.split("STEP pilot_api_verify", 1)[1].split("trap -", 1)[0]
    assert "exit 12" in text


def test_pilot_api_verify_no_ephemeral_api_container(require_ops_scripts: None) -> None:
    text = _VERIFY.read_text(encoding="utf-8")
    assert "server_pilot_api_up.sh" in text
    assert "linkedin-pilot-api-verify" not in text
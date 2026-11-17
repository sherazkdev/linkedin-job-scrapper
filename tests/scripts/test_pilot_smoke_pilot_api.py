from pathlib import Path

_REPO = Path(__file__).resolve().parents[2]


def test_pilot_software_engineer_reuses_persistent_pilot_api() -> None:
    text = (_REPO / "scripts/server_pilot_software_engineer.sh").read_text(encoding="utf-8")
    assert "server_pilot_api_up.sh" in text
    assert "linkedin-pilot-api-verify" not in text.split("STEP pilot_api_verify", 1)[1].split("trap -", 1)[0]
    assert "exit 12" in text


def test_pilot_api_verify_no_ephemeral_api_container() -> None:
    text = (_REPO / "scripts/server_pilot_api_verify.sh").read_text(encoding="utf-8")
    assert "server_pilot_api_up.sh" in text
    assert "linkedin-pilot-api-verify" not in text
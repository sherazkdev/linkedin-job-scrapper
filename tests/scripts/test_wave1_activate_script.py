from pathlib import Path

import pytest

_REPO = Path(__file__).resolve().parents[2]
_SCRIPT = _REPO / "scripts/server_wave1_activate.sh"


@pytest.fixture(scope="module")
def wave1_activate_script() -> str:
    if not _SCRIPT.is_file():
        pytest.skip("Wave 1 ops scripts not in pytest image")
    return _SCRIPT.read_text(encoding="utf-8")


def test_wave1_activate_waits_worker_before_beat(wave1_activate_script: str) -> None:
    assert "STEP wait_worker_ready" in wave1_activate_script
    beat_idx = wave1_activate_script.index("STEP start_beat")
    worker_idx = wave1_activate_script.index("STEP wait_worker_ready")
    observer_idx = wave1_activate_script.index("STEP start_observer")
    assert worker_idx < observer_idx < beat_idx


def test_wave1_activate_uses_worker_ready_not_ping_only(wave1_activate_script: str) -> None:
    assert "worker-ready" in wave1_activate_script
    assert "celery_ops ping" not in wave1_activate_script


def test_wave1_activate_failure_cleanup_trap(wave1_activate_script: str) -> None:
    assert "server_wave1_stop.sh activation_failed" in wave1_activate_script
    assert "trap wave1_activation_cleanup EXIT" in wave1_activate_script
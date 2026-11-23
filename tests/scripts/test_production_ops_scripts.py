from pathlib import Path

import pytest

_REPO = Path(__file__).resolve().parents[2]


@pytest.fixture(scope="module")
def _require_scripts() -> None:
    needed = [
        _REPO / "scripts/server_wave1_observer.sh",
        _REPO / "scripts/server_publication_sync_scheduled.sh",
        _REPO / "scripts/server_job_expiry_scheduled.sh",
        _REPO / "scripts/server_publication_lifecycle_scheduled.sh",
        _REPO / "scripts/server_install_production_ops_cron.sh",
    ]
    if not all(p.is_file() for p in needed):
        pytest.skip("Ops scripts not in pytest image")


def test_observer_continuous_no_24h_shutdown(_require_scripts: None) -> None:
    text = (_REPO / "scripts/server_wave1_observer.sh").read_text(encoding="utf-8")
    assert "mode=continuous" in text
    assert "while true" in text
    assert "observation_24h_complete" not in text
    assert "worker-ready" in text or "celery_ops" in text


def test_publication_sync_no_auto_deprecate(_require_scripts: None) -> None:
    text = (_REPO / "scripts/server_publication_sync_scheduled.sh").read_text(encoding="utf-8")
    assert "sync-apply" in text
    assert "--deprecate" not in text
    assert "ALLOW_SCHEDULED_PUBLICATION_SYNC" in text
    assert "reconcile" in text
    assert "ALLOW_PILOT_TO_PRODUCTION_PROMOTION=true" in text


def test_production_ops_cron_schedule(_require_scripts: None) -> None:
    text = (_REPO / "scripts/server_install_production_ops_cron.sh").read_text(encoding="utf-8")
    assert "CRON_TZ=UTC" in text
    assert "*/10 * * * *" in text
    assert "30 */6 * * *" in text
    assert "server_wave1_observer_check.sh" in text
    assert "server_publication_sync_scheduled.sh" in text


def test_job_expiry_scheduled_gates(_require_scripts: None) -> None:
    text = (_REPO / "scripts/server_job_expiry_scheduled.sh").read_text(encoding="utf-8")
    assert "ALLOW_SCHEDULED_JOB_EXPIRY" in text
    assert "flock" in text
    assert "expire-preview" in text
    assert "JOB_EXPIRY_PRODUCTION_APPLY" in text
    assert "server_mongo_backup_jobs.sh" in text


def test_lifecycle_sync_scheduled_gates(_require_scripts: None) -> None:
    text = (_REPO / "scripts/server_publication_lifecycle_scheduled.sh").read_text(encoding="utf-8")
    assert "lifecycle-preview" in text
    assert "ALLOW_SCHEDULED_LIFECYCLE_PUBLICATION" in text
    assert "ALLOW_MASS_LIFECYCLE_DEPRECATION" in text
    assert "flock" in text
from app.core.config import get_settings
from app.modules.scheduling.rollout import estimate_daily_throughput, load_rollout_config


def test_rollout_config_loads() -> None:
    cfg = load_rollout_config()
    assert cfg["schema_version"] == 1
    assert len(cfg["waves"]) >= 5


def test_throughput_estimate_bounded() -> None:
    settings = get_settings()
    est = estimate_daily_throughput(settings)
    daily = est["estimated_completed_runs_per_day"]
    assert 10 <= daily <= 2000
    assert est["full_manifest_rotation_days_recommended_ops"] > 1
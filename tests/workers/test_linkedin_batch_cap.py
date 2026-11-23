from app.core.config import Settings
from app.workers.linkedin_batch_cap import resolve_linkedin_max_jobs_per_run


def _settings(**overrides: object) -> Settings:
    base = {
        "MONGO_URI": "mongodb://localhost:27017",
        "REDIS_URL": "redis://localhost:6379/0",
        "linkedin_max_live_jobs_per_run": 5,
        "linkedin_max_jobs_per_run_hard_cap": 15,
    }
    base.update(overrides)
    return Settings(**base).model_copy(update=overrides)


def test_default_soft_cap_limits_trial_without_honor() -> None:
    s = _settings(allow_live_linkedin_collection=True, linkedin_honor_target_batch_sizes=False)
    assert resolve_linkedin_max_jobs_per_run(10, s) == 5
    assert resolve_linkedin_max_jobs_per_run(15, s) == 5


def test_honor_target_allows_10_and_15_trials() -> None:
    s = _settings(
        allow_live_linkedin_collection=True,
        linkedin_honor_target_batch_sizes=True,
    )
    assert resolve_linkedin_max_jobs_per_run(10, s) == 10
    assert resolve_linkedin_max_jobs_per_run(15, s) == 15
    assert resolve_linkedin_max_jobs_per_run(20, s) == 15


def test_offline_cap_uses_hard_cap_only() -> None:
    s = _settings(allow_live_linkedin_collection=False, linkedin_honor_target_batch_sizes=False)
    assert resolve_linkedin_max_jobs_per_run(12, s) == 12
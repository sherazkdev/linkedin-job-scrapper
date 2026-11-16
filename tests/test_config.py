import pytest
from pydantic import ValidationError

from app.core.config import Settings, get_settings


def test_settings_loads_required_fields(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MONGO_URI", "mongodb://user:pass@localhost:27017")
    monkeypatch.setenv("REDIS_URL", "redis://:pass@localhost:6379/0")
    get_settings.cache_clear()
    settings = Settings()
    assert settings.mongo_uri.startswith("mongodb://")
    assert settings.redis_url.startswith("redis://")
    get_settings.cache_clear()


def test_settings_rejects_missing_mongo_uri(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("MONGO_URI", raising=False)
    monkeypatch.setenv("REDIS_URL", "redis://:pass@localhost:6379/0")
    get_settings.cache_clear()
    with pytest.raises(ValidationError):
        Settings(_env_file=None)
    get_settings.cache_clear()

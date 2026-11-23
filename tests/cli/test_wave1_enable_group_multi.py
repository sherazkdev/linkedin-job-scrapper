import json
from pathlib import Path
from unittest.mock import patch

import pytest

from app.cli import wave1_ops
from app.core.config import Settings


@pytest.mark.asyncio
async def test_enable_group_multi_keyword(integration_db: None) -> None:
    from app.database.temp_database import open_database

    settings = Settings(
        MONGO_URI="mongodb://localhost:27017",
        REDIS_URL="redis://localhost:6379/0",
        celery_worker_mongo_db_name="global_jobs_pilot",
        allow_live_linkedin_collection=True,
        celery_allow_linkedin_tasks=True,
        celery_dispatch_max_per_tick=1,
        linkedin_max_live_runs_per_24h=30,
        linkedin_honor_target_batch_sizes=True,
    )
    groups_path = Path(__file__).resolve().parents[2] / "config" / "wave1_keyword_groups.json"
    payload = json.loads(groups_path.read_text(encoding="utf-8"))
    payload["groups"]["test_pair"] = {
        "keywords": ["backend developer", "frontend developer"],
        "default_max_jobs_per_run": 5,
        "max_enabled_targets": 4,
        "priority": 50,
    }
    tmp_groups = groups_path.parent / "_test_wave1_groups.json"
    tmp_groups.write_text(json.dumps(payload), encoding="utf-8")
    db_name = "global_jobs_test_pilot"
    with patch.object(wave1_ops, "get_settings", return_value=settings):
        with patch.object(wave1_ops, "KEYWORD_GROUPS_PATH", tmp_groups):
            with patch.object(wave1_ops, "_manifest_country_codes", return_value=["US", "GB"]):
                with patch.object(wave1_ops, "_assert_pilot_db_only"):
                    with patch.object(wave1_ops, "_assert_scheduler_gates"):
                        code = await wave1_ops._enable_group(
                            db_name,
                            group_name="test_pair",
                            max_jobs=None,
                        )
    assert code == 0
    async with open_database(db_name) as database:
        enabled = await database["collection_targets"].count_documents(
            {"source": "linkedin", "enabled": True}
        )
        assert enabled == 4
    tmp_groups.unlink(missing_ok=True)
from unittest.mock import MagicMock, patch

import pytest

from app.cli import celery_ops


def test_pilot_dispatch_once_uses_unique_task_id() -> None:
    captured: dict = {}

    def fake_apply_async(*, kwargs, queue, task_id):
        captured["kwargs"] = kwargs
        captured["queue"] = queue
        captured["task_id"] = task_id

    with patch("app.workers.tasks.run_collection_task") as task_mock:
        task_mock.apply_async = MagicMock(side_effect=fake_apply_async)
        with patch.object(celery_ops, "get_settings") as settings_mock:
            settings_mock.return_value.celery_task_default_queue = "collection"
            with patch.object(
                celery_ops.sys,
                "argv",
                [
                    "celery_ops",
                    "pilot-dispatch-once",
                    "--keyword",
                    "junior erp consultant",
                ],
            ):
                with patch.object(celery_ops, "configure_logging"):
                    with pytest.raises(SystemExit) as exc:
                        celery_ops.main()
                    assert exc.value.code == 0

    assert captured["task_id"].startswith("pilot-linkedin-PK-junior_erp_consultant-")
    assert len(captured["task_id"]) > len("pilot-linkedin-PK-junior_erp_consultant-")
    assert captured["kwargs"]["max_jobs"] == 1
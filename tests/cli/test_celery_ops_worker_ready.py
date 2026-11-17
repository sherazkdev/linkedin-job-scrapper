import json
from unittest.mock import MagicMock, patch

import pytest

from app.cli import celery_ops


def test_worker_ready_cli_busy_solo_exits_zero() -> None:
    inspector = MagicMock()
    inspector.ping.return_value = None
    inspector.registered.return_value = None
    inspector.active.return_value = {
        "linkedin-worker@vps": [{"name": "app.workers.tasks.run_collection_task"}]
    }

    with patch.object(celery_ops, "get_settings") as settings_mock:
        settings_mock.return_value.celery_task_default_queue = "collection"
        with patch.object(celery_ops.celery_app.control, "inspect", return_value=inspector):
            with patch.object(celery_ops, "configure_logging"):
                with patch.object(
                    celery_ops.sys,
                    "argv",
                    ["celery_ops", "worker-ready", "--timeout", "3"],
                ):
                    with patch("builtins.print") as print_mock:
                        with pytest.raises(SystemExit) as exc:
                            celery_ops.main()
                        assert exc.value.code == 0

    payload = json.loads(print_mock.call_args[0][0])
    assert payload["ok"] is True
    assert payload["method"] == "solo_executing_task"
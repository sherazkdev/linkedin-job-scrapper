from app.workers.readiness import evaluate_worker_readiness


def test_readiness_ping_ok() -> None:
    out = evaluate_worker_readiness(
        ping={"linkedin-worker@host": {"ok": "pong"}},
        registered=None,
        active=None,
    )
    assert out["ok"] is True
    assert out["method"] == "inspect_ping"


def test_readiness_registered_when_ping_missing() -> None:
    out = evaluate_worker_readiness(
        ping={},
        registered={"linkedin-worker@host": ["app.workers.tasks.run_collection_task"]},
        active={},
    )
    assert out["ok"] is True
    assert out["method"] == "inspect_registered"


def test_readiness_solo_busy_executing_not_dead() -> None:
    out = evaluate_worker_readiness(
        ping=None,
        registered=None,
        active={
            "linkedin-worker@abc": [
                {"name": "app.workers.tasks.run_collection_task", "id": "1"}
            ]
        },
        pool="solo",
    )
    assert out["ok"] is True
    assert out["busy"] is True
    assert out["method"] == "solo_executing_task"


def test_readiness_unavailable_when_no_signals() -> None:
    out = evaluate_worker_readiness(ping={}, registered={}, active={}, pool="solo")
    assert out["ok"] is False
    assert out["method"] == "unavailable"
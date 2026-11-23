from app.modules.alerts.constants import EVENT_JOB_UPDATED, EVENT_NEW_JOB, EVENT_REACTIVATED
from app.modules.alerts.matcher import event_key_for_outcome


def test_event_key_created() -> None:
    assert (
        event_key_for_outcome(created=True, updated=False, reactivated=False) == EVENT_NEW_JOB
    )


def test_event_key_updated() -> None:
    assert (
        event_key_for_outcome(created=False, updated=True, reactivated=False)
        == EVENT_JOB_UPDATED
    )


def test_event_key_reactivated() -> None:
    assert (
        event_key_for_outcome(created=False, updated=False, reactivated=True) == EVENT_REACTIVATED
    )


def test_event_key_unchanged_returns_none() -> None:
    assert event_key_for_outcome(created=False, updated=False, reactivated=False) is None
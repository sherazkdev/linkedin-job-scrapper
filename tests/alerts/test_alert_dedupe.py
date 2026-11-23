from app.modules.alerts.service import dedupe_alert_event, job_eligible_for_alert


def test_alert_dedupe_skips_repeat() -> None:
    seen: set[str] = set()
    first = dedupe_alert_event(
        subscriber_id="sub1", job_id="job1", event_key="new_job", seen_events=seen
    )
    second = dedupe_alert_event(
        subscriber_id="sub1", job_id="job1", event_key="new_job", seen_events=seen
    )
    assert first is not None
    assert second is None


def test_expired_jobs_not_alert_eligible() -> None:
    from datetime import UTC, datetime, timedelta

    doc = {
        "status": "active",
        "posted_at": datetime.now(UTC) - timedelta(days=30),
        "first_seen_at": datetime.now(UTC) - timedelta(days=30),
    }
    assert not job_eligible_for_alert(doc, max_age_days=7)
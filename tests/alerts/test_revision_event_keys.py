from app.modules.alerts.matcher import event_key_for_outcome
from app.modules.alerts.revision import alert_revision_fingerprint


def test_updated_event_key_changes_with_content() -> None:
    job_a = {"title": "Engineer", "company": "A"}
    job_b = {"title": "Senior Engineer", "company": "A"}
    ka = event_key_for_outcome(created=False, updated=True, reactivated=False, job=job_a)
    kb = event_key_for_outcome(created=False, updated=True, reactivated=False, job=job_b)
    assert ka != kb
    assert ka.startswith("job_updated:")
    assert alert_revision_fingerprint(job_a) in ka


def test_duplicate_same_revision_same_key() -> None:
    job = {"title": "Engineer", "company": "A", "city": "Islamabad"}
    k1 = event_key_for_outcome(created=False, updated=True, reactivated=False, job=job)
    k2 = event_key_for_outcome(created=False, updated=True, reactivated=False, job=job)
    assert k1 == k2
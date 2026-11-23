from app.core.config import Settings
from app.workers.dispatcher import target_max_jobs


def test_live_linkedin_respects_hard_cap(monkeypatch) -> None:
    settings = Settings(
        MONGO_URI="mongodb://localhost:27017",
        REDIS_URL="redis://localhost:6379/0",
        linkedin_max_live_jobs_per_run=5,
        linkedin_max_jobs_per_run_hard_cap=15,
        celery_collection_max_jobs_default=10,
    ).model_copy(
        update={
            "allow_live_linkedin_collection": True,
            "linkedin_honor_target_batch_sizes": False,
        }
    )
    doc = {"source": "linkedin", "max_jobs_per_run": 20}
    assert target_max_jobs(doc, settings) == 5
    doc2 = {"source": "linkedin", "max_jobs_per_run": 10}
    assert target_max_jobs(doc2, settings) == 5
    honor = settings.model_copy(update={"linkedin_honor_target_batch_sizes": True})
    assert target_max_jobs(doc2, honor) == 10
    offline = settings.model_copy(update={"allow_live_linkedin_collection": False})
    assert target_max_jobs(doc, offline) == 15
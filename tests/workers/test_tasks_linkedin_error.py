import pytest

from app.modules.collection.linkedin.errors import LinkedInCollectionError, LinkedInFailureState
from app.workers.tasks import run_collection_task


@pytest.fixture
def celery_eager(monkeypatch: pytest.MonkeyPatch) -> None:
    from app.workers.celery_app import celery_app

    celery_app.conf.task_always_eager = True
    celery_app.conf.task_eager_propagates = True


def test_linkedin_error_mapped_for_celery_serialization(
    monkeypatch: pytest.MonkeyPatch, celery_eager: None
) -> None:
    def _raise(*_a: object, **_k: object) -> None:
        raise LinkedInCollectionError(
            LinkedInFailureState.PAGE_UNRESPONSIVE,
            "probe failed",
            retryable=False,
        )

    monkeypatch.setattr(
        "app.workers.tasks.run_collection_sync",
        _raise,
    )
    with pytest.raises(RuntimeError, match="linkedin:page_unresponsive"):
        run_collection_task.apply(
            kwargs={
                "source": "linkedin",
                "country_code": "PK",
                "keyword": "junior erp consultant",
                "max_jobs": 1,
                "search_location": "Islamabad, Pakistan",
            }
        )
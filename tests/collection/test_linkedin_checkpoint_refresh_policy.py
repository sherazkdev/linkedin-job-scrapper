"""SERP processed_ids must not block Mongo upsert refresh on a new run."""

from app.modules.collection.linkedin.checkpoint_policy import prepare_linkedin_run_checkpoint


def test_stored_processed_ids_never_skip_page_zero_cards_on_next_run() -> None:
    """Regression: page_index=8 + huge processed_ids used to skip re-collection."""
    stored = {
        "page_index": 8,
        "processed_ids": [str(i) for i in range(500)],
        "processed_ids_last_run_count": 500,
    }
    prepared = prepare_linkedin_run_checkpoint(stored, ignore_stored=False)
    assert prepared is not None
    assert prepared["page_index"] == 0
    assert prepared["processed_ids"] == []
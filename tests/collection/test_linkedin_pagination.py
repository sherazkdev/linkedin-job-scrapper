from app.modules.collection.linkedin.pagination import (
    LINKEDIN_SEARCH_PAGE_SIZE,
    compute_search_has_more,
    search_page_has_next_page,
)


def test_search_page_has_next_page_full() -> None:
    assert search_page_has_next_page(cards_on_page=LINKEDIN_SEARCH_PAGE_SIZE) is True


def test_search_page_has_next_page_partial() -> None:
    assert search_page_has_next_page(cards_on_page=14) is False


def test_has_more_false_when_limit_met() -> None:
    assert (
        compute_search_has_more(
            jobs_collected=5,
            limit=5,
            cards_on_last_page=25,
        )
        is False
    )


def test_has_more_false_when_partial_page_all_rejected() -> None:
    assert (
        compute_search_has_more(
            jobs_collected=0,
            limit=5,
            cards_on_last_page=14,
        )
        is False
    )


def test_has_more_true_when_full_page_below_limit() -> None:
    assert (
        compute_search_has_more(
            jobs_collected=0,
            limit=5,
            cards_on_last_page=25,
        )
        is True
    )
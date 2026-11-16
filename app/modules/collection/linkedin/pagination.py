"""LinkedIn job search pagination helpers (bounded, no duplicate page semantics)."""

LINKEDIN_SEARCH_PAGE_SIZE = 25


def search_page_has_next_page(*, cards_on_page: int) -> bool:
    """LinkedIn typically returns 25 cards when another page may exist."""
    return cards_on_page >= LINKEDIN_SEARCH_PAGE_SIZE


def compute_search_has_more(
    *,
    jobs_collected: int,
    limit: int,
    cards_on_last_page: int,
) -> bool:
    if jobs_collected >= limit:
        return False
    return search_page_has_next_page(cards_on_page=cards_on_last_page)
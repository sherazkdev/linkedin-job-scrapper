import pytest
from pydantic import ValidationError

from app.modules.jobs.schemas.job import PaginationParams


def test_pagination_bounds() -> None:
    params = PaginationParams(page=1, page_size=50)
    assert params.page_size == 50

    with pytest.raises(ValidationError):
        PaginationParams(page=0, page_size=10)

    with pytest.raises(ValidationError):
        PaginationParams(page=1, page_size=0)

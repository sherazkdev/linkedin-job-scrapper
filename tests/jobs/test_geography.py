import pytest

from app.modules.jobs.geography import resolve_geography


@pytest.mark.parametrize(
    "search,location,expected_country,remote",
    [
        ("PK", "Karachi, Pakistan", "PK", None),
        ("DE", "Berlin, Germany", "DE", None),
        ("US", "Austin, Texas, United States", "US", None),
        ("US", "Tampa, FL", "US", None),
        ("GB", "London, United Kingdom", "GB", None),
        ("AE", "Dubai, United Arab Emirates", "AE", None),
        ("US", "Berlin, Germany", "DE", None),
        ("DE", "Remote", None, True),
        ("US", "Remote, United States", "US", True),
        ("DE", "European Union", None, None),
    ],
)
def test_resolve_geography_cases(
    search: str,
    location: str,
    expected_country: str | None,
    remote: bool | None,
) -> None:
    result = resolve_geography(
        search_country_code=search,
        location_text=location,
        workplace_type="remote" if remote else None,
    )
    assert result.search_country_code == search
    assert result.country_code == expected_country
    assert result.location_text == location
    if remote is not None:
        assert result.is_remote is True or (remote is False and result.is_remote is not True)
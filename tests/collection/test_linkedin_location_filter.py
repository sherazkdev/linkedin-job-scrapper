from urllib.parse import parse_qs, urlparse

from app.modules.collection.linkedin.adapter import _build_search_url
from app.modules.collection.linkedin.location_filter import (
    job_matches_search_location,
    resolve_search_location,
)


def test_build_search_url_islamabad_past_24h() -> None:
    url = _build_search_url(
        keyword="Software Engineer",
        location="Islamabad, Pakistan",
        start=0,
        past_24h=True,
        sort_recent=True,
    )
    qs = parse_qs(urlparse(url).query)
    assert qs["keywords"] == ["Software Engineer"]
    assert qs["location"] == ["Islamabad, Pakistan"]
    assert qs["f_TPR"] == ["r86400"]
    assert qs["sortBy"] == ["DD"]


def test_resolve_search_location_override() -> None:
    assert resolve_search_location("PK", "Islamabad, Pakistan") == "Islamabad, Pakistan"
    assert resolve_search_location("PK", None) == "Pakistan"


def test_job_matches_islamabad_excludes_other_cities() -> None:
    assert job_matches_search_location("Islamabad, Pakistan", "Islamabad, Pakistan")
    assert not job_matches_search_location("Rawalpindi, Pakistan", "Islamabad, Pakistan")
    assert not job_matches_search_location("Lahore, Pakistan", "Islamabad, Pakistan")
    assert not job_matches_search_location("Karachi, Pakistan", "Islamabad, Pakistan")
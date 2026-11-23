from bs4 import BeautifulSoup

from app.modules.collection.linkedin.parser import _extract_employment


def test_part_time_from_listing_insight_en() -> None:
    html = '<html><span class="job-details-jobs-unified-top-card__job-insight"><span>Part-time</span></span></html>'
    soup = BeautifulSoup(html, "html.parser")
    assert _extract_employment(soup) == "part_time"


def test_part_time_japanese_label() -> None:
    html = '<html><span class="description__job-criteria-item">パートタイム</span></html>'
    soup = BeautifulSoup(html, "html.parser")
    # Parser only detects English phrases today; keyword alone must not set employment downstream.
    assert _extract_employment(soup) is None


def test_full_time_korean_context() -> None:
    html = '<html><span class="description__job-criteria-item">정규직 Full-time</span></html>'
    soup = BeautifulSoup(html, "html.parser")
    assert _extract_employment(soup) == "full_time"
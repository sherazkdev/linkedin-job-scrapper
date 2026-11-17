from datetime import UTC, datetime

from app.workers.fair_dispatch import fair_country_round_robin


def _doc(country: str, keyword: str, *, priority: int = 0) -> dict:
    return {
        "country_code": country,
        "keyword": keyword,
        "priority": priority,
        "next_eligible_at": datetime.now(UTC),
    }


def test_fair_dispatch_one_per_country_before_repeat() -> None:
    targets = [
        _doc("US", "a"),
        _doc("US", "b"),
        _doc("GB", "a"),
        _doc("DE", "a"),
    ]
    ordered = fair_country_round_robin(targets, limit=3)
    countries = [t["country_code"] for t in ordered]
    assert len(set(countries)) == 3
    assert countries[0] in {"DE", "GB", "US"}


def test_fair_dispatch_respects_limit() -> None:
    targets = [_doc("US", "a"), _doc("GB", "a")]
    assert len(fair_country_round_robin(targets, limit=1)) == 1
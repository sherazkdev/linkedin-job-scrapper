from app.modules.promotion.lifecycle_sync_safety import assess_deprecation_plan


def test_mass_expiry_requires_approval() -> None:
    safety = assess_deprecation_plan(
        {"would_deprecate_count": 300, "would_deprecate_reasons": []},
        production_published_count=415,
    )
    assert safety["mass_deprecate_risk"] is True
    assert safety["requires_explicit_mass_approval"] is True


def test_small_deprecate_allowed() -> None:
    safety = assess_deprecation_plan(
        {"would_deprecate_count": 5, "would_deprecate_reasons": []},
        production_published_count=415,
    )
    assert safety["mass_deprecate_risk"] is False
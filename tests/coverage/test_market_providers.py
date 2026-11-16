from app.modules.coverage.market_providers import build_country_capability_matrix, matrix_summary


def test_matrix_has_40_countries() -> None:
    matrix = build_country_capability_matrix()
    assert len(matrix) == 40
    codes = {row["iso_code"] for row in matrix}
    assert len(codes) == 40
    assert "PK" in codes
    assert "AE" in codes


def test_matrix_summary_counts() -> None:
    summary = matrix_summary()
    assert summary["countries_in_manifest"] == 40
    assert summary["countries_with_any_verified_provider"] >= 20
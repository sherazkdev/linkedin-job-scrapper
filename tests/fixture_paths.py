from pathlib import Path

_TESTS = Path(__file__).resolve().parent
REPO_ROOT = _TESTS.parent

LINKEDIN_FIXTURES = REPO_ROOT / "app" / "modules" / "collection" / "linkedin" / "fixtures"
GREENHOUSE_SAMPLE = _TESTS / "fixtures" / "public_boards" / "greenhouse" / "sample.json"
ADZUNA_US_PAGE1 = _TESTS / "fixtures" / "market_search" / "adzuna" / "us_page1.json"
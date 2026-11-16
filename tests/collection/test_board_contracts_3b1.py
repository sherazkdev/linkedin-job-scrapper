import json
from datetime import UTC, datetime
from pathlib import Path

import pytest

from app.modules.collection.boards.parsers import (
    ashby_jobs_to_raw,
    greenhouse_jobs_to_raw,
)
from app.modules.collection.boards.validation import validate_board_site
from app.modules.collection.http.client import PublicBoardHttpClient
from app.modules.collection.http.errors import PublicBoardCollectionError, PublicBoardFailureState
from app.modules.collection.http.hosts import assert_approved_url

FIXTURE_ROOT = Path(__file__).resolve().parents[1] / "fixtures" / "public_boards"


def test_greenhouse_uses_first_published_not_updated_at() -> None:
    payload = json.loads((FIXTURE_ROOT / "greenhouse" / "sample.json").read_text(encoding="utf-8"))
    jobs, metrics = greenhouse_jobs_to_raw(
        payload["jobs_payload"],
        board_site="sample",
        company_name="Sample Public Co",
        search_country_code="US",
        keyword="engineer",
        skip_ids=set(),
        limit=5,
    )
    assert metrics["valid_listings"] == 1
    assert jobs[0].posted_at == datetime(2025, 10, 1, 12, 0, tzinfo=UTC)
    assert metrics["keyword_rejected"] == 1  # sales role excluded by keyword filter


def test_ashby_skips_unlisted_jobs() -> None:
    payload = json.loads((FIXTURE_ROOT / "ashby" / "sample.json").read_text(encoding="utf-8"))
    jobs, metrics = ashby_jobs_to_raw(
        payload["board_payload"],
        board_site="sample",
        company_name="Ashby Sample",
        search_country_code="GB",
        keyword="*",
        skip_ids=set(),
        limit=5,
    )
    assert metrics["unlisted_skipped"] == 1
    assert len(jobs) == 1
    assert jobs[0].source_job_id == "sample:ashby-job-uuid-1"


def test_board_site_validation_rejects_path_traversal() -> None:
    with pytest.raises(PublicBoardCollectionError):
        validate_board_site("../../etc")


def test_only_approved_hosts() -> None:
    assert_approved_url("https://boards-api.greenhouse.io/v1/boards/stripe/jobs")
    with pytest.raises(ValueError):
        assert_approved_url("https://evil.example.com/jobs")


@pytest.mark.asyncio
async def test_http_client_forbidden_403() -> None:
    def handler(request):  # noqa: ANN001
        return __import__("httpx").Response(403)

    import httpx

    client = PublicBoardHttpClient(timeout_seconds=5.0, min_interval_seconds=0)
    client._client = httpx.AsyncClient(  # type: ignore[attr-defined]
        transport=httpx.MockTransport(handler),
        base_url="https://boards-api.greenhouse.io",
    )
    with pytest.raises(PublicBoardCollectionError) as exc:
        await client.get_json("https://boards-api.greenhouse.io/v1/boards/x/jobs")
    assert exc.value.state == PublicBoardFailureState.FORBIDDEN
    await client.aclose()
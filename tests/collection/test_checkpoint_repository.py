import pytest

from app.database.temp_database import open_database
from app.modules.collection.repositories.checkpoint_repository import (
    CheckpointRepository,
    normalize_checkpoint_search_location,
)
from app.modules.jobs.models.job import JobSource


def test_normalize_checkpoint_search_location() -> None:
    assert normalize_checkpoint_search_location(None) == ""
    assert normalize_checkpoint_search_location("") == ""
    assert normalize_checkpoint_search_location("  ") == ""
    assert normalize_checkpoint_search_location("Islamabad, Pakistan") == "islamabad, pakistan"


@pytest.mark.asyncio
async def test_checkpoint_isolated_by_search_location(integration_db: None) -> None:
    keyword = "__pytest_checkpoint_loc_isolation__"
    async with open_database("global_jobs_test") as database:
        repo = CheckpointRepository(database)
        base = {
            "source": JobSource.LINKEDIN,
            "country_code": "PK",
            "keyword": keyword,
        }
        filter_doc = {
            "source": JobSource.LINKEDIN.value,
            "country_code": "PK",
            "keyword": keyword,
        }
        await database["collection_checkpoints"].delete_many(filter_doc)
        try:
            await repo.save(
                **base,
                search_location="Islamabad, Pakistan",
                checkpoint={"page_index": 2, "processed_ids": ["a"]},
            )
            await repo.save(
                **base,
                search_location="Rawalpindi, Pakistan",
                checkpoint={"page_index": 5, "processed_ids": ["b"]},
            )

            isb = await repo.load(**base, search_location="Islamabad, Pakistan")
            rwp = await repo.load(**base, search_location="Rawalpindi, Pakistan")
            wide = await repo.load(**base, search_location=None)
            country_wide = await repo.load(**base, search_location="")

            assert isb == {"page_index": 2, "processed_ids": ["a"]}
            assert rwp == {"page_index": 5, "processed_ids": ["b"]}
            assert wide is None
            assert country_wide is None
        finally:
            await database["collection_checkpoints"].delete_many(filter_doc)
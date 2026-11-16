import pytest

from app.database.indexes import JOBS_COLLECTION
from app.database.mongodb import get_mongodb


@pytest.mark.asyncio
async def test_job_indexes_exist(integration_db: None) -> None:
    collection = get_mongodb().database[JOBS_COLLECTION]
    indexes = await collection.index_information()
    assert "uniq_source_source_job_id" in indexes
    assert indexes["uniq_source_source_job_id"].get("unique") is True
    key_fields = indexes["uniq_source_source_job_id"]["key"]
    assert ("source", 1) in key_fields
    assert ("sourceJobId", 1) in key_fields

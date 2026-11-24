from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.modules.alerts.repositories import DigestStateRepository, SavedSearchRepository


@pytest.mark.asyncio
async def test_update_rejects_conflict_before_mutation() -> None:
    db = MagicMock()
    repo = SavedSearchRepository(db)
    repo._col = MagicMock()
    repo._col.find_one_and_update = AsyncMock()
    repo.get_owned = AsyncMock(
        return_value={
            "search_id": "s1",
            "subscriber_id": "sub-1",
            "digest_enabled": True,
            "digest_timezone": "UTC",
            "digest_local_time": "09:00",
            "digest_max_jobs": 10,
        }
    )
    with patch.object(
        repo._digest_state,
        "assert_schedule_compatible",
        AsyncMock(side_effect=ValueError("conflict")),
    ):
        with pytest.raises(ValueError, match="conflict"):
            await repo.update_owned(
                subscriber_id="sub-1",
                search_id="s1",
                updates={"digest_timezone": "Asia/Karachi"},
            )
    repo._col.find_one_and_update.assert_not_called()
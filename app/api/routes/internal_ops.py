from typing import Annotated, Any

from fastapi import APIRouter, Depends, Header, HTTPException, status
from pymongo.asynchronous.database import AsyncDatabase

from app.api.deps import get_db
from app.core.config import Settings, get_settings
from app.core.security import verify_internal_token
from app.modules.coverage.report import build_coverage_report
from app.modules.operations.monitoring import build_operations_snapshot

router = APIRouter(prefix="/internal/v1", tags=["internal"])


def require_internal_token(
    settings: Annotated[Settings, Depends(get_settings)],
    x_internal_ops_token: Annotated[str | None, Header()] = None,
) -> None:
    expected = settings.internal_ops_token
    if not expected:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Internal operations disabled",
        )
    if not verify_internal_token(x_internal_ops_token, expected):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Unauthorized")


@router.get("/monitoring/snapshot")
async def monitoring_snapshot(
    _: Annotated[None, Depends(require_internal_token)],
    database: Annotated[AsyncDatabase[Any], Depends(get_db)],
) -> dict[str, Any]:
    return await build_operations_snapshot(database)


@router.get("/monitoring/coverage")
async def monitoring_coverage(
    _: Annotated[None, Depends(require_internal_token)],
    database: Annotated[AsyncDatabase[Any], Depends(get_db)],
) -> dict[str, Any]:
    return await build_coverage_report(database)
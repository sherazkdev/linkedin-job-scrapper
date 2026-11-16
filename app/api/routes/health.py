from typing import Annotated, Any

from fastapi import APIRouter, Depends, status
from fastapi.responses import JSONResponse

from app.api.deps import get_redis_from_request
from app.database.mongodb import get_mongodb
from app.database.redis_client import RedisClient

router = APIRouter(tags=["health"])


@router.get("/health/live")
async def liveness() -> dict[str, Any]:
    return {"success": True, "status": "live"}


@router.get("/health/ready")
async def readiness(
    redis: Annotated[RedisClient, Depends(get_redis_from_request)],
) -> JSONResponse:
    mongo_ok = await get_mongodb().ping()
    redis_ok = await redis.ping()
    ready = mongo_ok and redis_ok
    body = {
        "success": ready,
        "status": "ready" if ready else "not_ready",
        "checks": {
            "mongodb": mongo_ok,
            "redis": redis_ok,
        },
    }
    code = status.HTTP_200_OK if ready else status.HTTP_503_SERVICE_UNAVAILABLE
    return JSONResponse(status_code=code, content=body)

from typing import Annotated

from fastapi import APIRouter, Depends

from app.api.deps import get_job_service
from app.modules.jobs.services.job_service import JobService

router = APIRouter(prefix="/api/v1/countries", tags=["countries"])


@router.get("", response_model=dict)
async def list_countries(service: Annotated[JobService, Depends(get_job_service)]) -> dict:
    data = await service.list_countries()
    return {
        "success": True,
        "data": {
            "job_countries": [c.model_dump(mode="json") for c in data["job_countries"]],
            "search_markets": [c.model_dump(mode="json") for c in data["search_markets"]],
        },
    }
from fastapi import APIRouter

from app.schemas.health_schemas import HealthResponse

router = APIRouter(prefix="/health", tags=["health"])


@router.get("", response_model=HealthResponse, summary="Check API availability")
def health_check() -> HealthResponse:
    return HealthResponse()

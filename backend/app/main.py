from fastapi import APIRouter, FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.v1.health_router import router as health_router

API_PREFIX = "/api/v1"


def create_app() -> FastAPI:
    application = FastAPI(
        title="AgroLogistix API",
        version="0.1.0",
        description="Bio-logistics planning API for Kaluga region",
    )
    application.add_middleware(
        CORSMiddleware,
        allow_origins=["http://localhost:5173", "http://localhost:4173"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    api_router = APIRouter(prefix=API_PREFIX)
    api_router.include_router(health_router)
    application.include_router(api_router)
    return application


app = create_app()

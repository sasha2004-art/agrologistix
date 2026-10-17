from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import APIRouter, FastAPI
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from sqlmodel import Session
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.api.v1.auth_router import router as auth_router
from app.api.v1.erp_router import router as erp_router, system_router
from app.api.v1.export_router import router as export_router
from app.api.v1.health_router import router as health_router
from app.api.v1.solver_router import router as solver_router
from app.api.v1.weather_router import router as weather_router
from app.core.config import Settings, get_settings
from app.core.database import create_database_engine, init_database
from app.core.errors import http_exception_handler, validation_exception_handler
from app.services.seed_kaluga import seed_database

API_PREFIX = "/api/v1"


@asynccontextmanager
async def lifespan(application: FastAPI) -> AsyncIterator[None]:
    with Session(application.state.db_engine) as session:
        seed_database(session)
    yield


def create_app(settings: Settings | None = None) -> FastAPI:
    resolved_settings = settings or get_settings()
    database_engine = create_database_engine(resolved_settings)
    init_database(database_engine)

    application = FastAPI(
        title="AgroLogistix API",
        version="0.1.0",
        description="Bio-logistics planning API for Kaluga region",
        lifespan=lifespan,
    )
    application.state.db_engine = database_engine
    application.add_exception_handler(StarletteHTTPException, http_exception_handler)
    application.add_exception_handler(RequestValidationError, validation_exception_handler)
    application.dependency_overrides[get_settings] = lambda: resolved_settings
    application.add_middleware(
        CORSMiddleware,
        allow_origins=resolved_settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    api_router = APIRouter(prefix=API_PREFIX)
    api_router.include_router(auth_router)
    api_router.include_router(health_router)
    api_router.include_router(erp_router)
    api_router.include_router(system_router)
    api_router.include_router(weather_router)
    api_router.include_router(solver_router)
    api_router.include_router(export_router)
    application.include_router(api_router)
    return application


app = create_app()

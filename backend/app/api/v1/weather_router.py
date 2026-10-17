from typing import Annotated

from fastapi import APIRouter, Depends
from sqlmodel import Session

from app.core.config import Settings, get_settings
from app.core.database import get_session
from app.core.security import AccessContext
from app.schemas.weather_schemas import WeatherOverrideRequest, WeatherResponse
from app.services.weather_service import (
    WeatherSnapshot,
    get_current_weather,
    write_weather_mode,
)

router = APIRouter(prefix="/weather", tags=["weather"])

SettingsDependency = Annotated[Settings, Depends(get_settings)]
SessionDependency = Annotated[Session, Depends(get_session)]


def _to_response(snapshot: WeatherSnapshot, settings: Settings) -> WeatherResponse:
    return WeatherResponse(
        latitude=settings.weather_latitude,
        longitude=settings.weather_longitude,
        temperature_c=snapshot.temperature_c,
        precipitation_mm=snapshot.precipitation_mm,
        weather_code=snapshot.weather_code,
        mode=snapshot.mode,
        fetched_at=snapshot.fetched_at,
    )


@router.get(
    "/current",
    response_model=WeatherResponse,
    summary="Read the active Kaluga weather and stress preset",
)
async def read_current_weather(
    context: AccessContext,
    session: SessionDependency,
    settings: SettingsDependency,
) -> WeatherResponse:
    snapshot = await get_current_weather(session, settings, account_id=context.account_id)
    return _to_response(snapshot, settings)


@router.post(
    "/override",
    response_model=WeatherResponse,
    summary="Persist and switch the manual weather preset",
)
async def override_weather(
    payload: WeatherOverrideRequest,
    context: AccessContext,
    session: SessionDependency,
    settings: SettingsDependency,
) -> WeatherResponse:
    write_weather_mode(session, payload.mode, account_id=context.account_id)
    snapshot = await get_current_weather(session, settings, account_id=context.account_id)
    return _to_response(snapshot, settings)

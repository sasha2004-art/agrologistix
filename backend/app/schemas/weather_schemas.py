from datetime import datetime

from pydantic import Field

from app.schemas.base import APIModel
from app.schemas.enums import WeatherMode


class WeatherOverrideRequest(APIModel):
    mode: WeatherMode


class WeatherResponse(APIModel):
    latitude: float
    longitude: float
    temperature_c: float
    precipitation_mm: float = Field(default=0.0, ge=0.0)
    weather_code: int | None = Field(default=None, ge=0)
    mode: WeatherMode
    fetched_at: datetime

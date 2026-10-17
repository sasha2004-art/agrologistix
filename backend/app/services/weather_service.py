"""Open-Meteo weather client with stress presets and a 15-minute cache.

The active preset (``normal`` / ``heatwave_35c`` / ``heavy_rain``) is persisted in
SQLite via :class:`WeatherOverrideState`, so the backend keeps a single source of
truth for the manual weather preset. Live Open-Meteo data is requested only in ``normal``
mode; the result (or the fallback) is cached in memory for the configured TTL to
keep the solver response below the two-second budget when the network is down.
"""

import logging
import time
from dataclasses import dataclass
from datetime import UTC, datetime

import httpx
from sqlmodel import Session, select

from app.core.config import Settings
from app.models.run_models import WeatherOverrideState
from app.schemas.enums import WeatherMode

logger = logging.getLogger(__name__)

OPEN_METEO_URL = "https://api.open-meteo.com/v1/forecast"


@dataclass(frozen=True, slots=True)
class PresetConditions:
    """Synthetic weather used by manual presets and offline fallback."""

    temperature_c: float
    precipitation_mm: float
    weather_code: int


# WMO weather codes: 0 = clear sky, 1 = mainly clear, 65 = heavy rain.
PRESET_CONDITIONS: dict[WeatherMode, PresetConditions] = {
    WeatherMode.HEATWAVE_35C: PresetConditions(
        temperature_c=35.0, precipitation_mm=0.0, weather_code=0
    ),
    WeatherMode.HEAVY_RAIN: PresetConditions(
        temperature_c=16.0, precipitation_mm=12.0, weather_code=65
    ),
}

# Used when Open-Meteo is unreachable while the ``normal`` preset is active.
FALLBACK_NORMAL = PresetConditions(temperature_c=20.0, precipitation_mm=0.0, weather_code=1)


@dataclass(frozen=True, slots=True)
class WeatherSnapshot:
    temperature_c: float
    precipitation_mm: float
    weather_code: int | None
    mode: WeatherMode
    fetched_at: datetime


@dataclass(slots=True)
class _CacheEntry:
    snapshot: WeatherSnapshot
    expires_at: float


_cache: dict[tuple[float, float], _CacheEntry] = {}


def reset_weather_cache() -> None:
    """Drop cached live weather (used by tests and ``reset-demo``)."""

    _cache.clear()


def _cache_key(settings: Settings) -> tuple[float, float]:
    return (settings.weather_latitude, settings.weather_longitude)


def read_weather_mode(session: Session, *, account_id: int) -> WeatherMode:
    """Read the persisted preset, creating the default row on first use."""

    state = session.exec(
        select(WeatherOverrideState).where(WeatherOverrideState.account_id == account_id)
    ).first()
    if state is None:
        state = WeatherOverrideState(account_id=account_id)
        session.add(state)
        session.commit()
    return WeatherMode(state.mode)


def write_weather_mode(session: Session, mode: WeatherMode, *, account_id: int) -> WeatherMode:
    """Persist a new preset and return it."""

    state = session.exec(
        select(WeatherOverrideState).where(WeatherOverrideState.account_id == account_id)
    ).first()
    if state is None:
        state = WeatherOverrideState(account_id=account_id, mode=mode.value)
    else:
        state.mode = mode.value
        state.updated_at = datetime.now(UTC)
    session.add(state)
    session.commit()
    return mode


def _snapshot(conditions: PresetConditions, mode: WeatherMode) -> WeatherSnapshot:
    return WeatherSnapshot(
        temperature_c=conditions.temperature_c,
        precipitation_mm=conditions.precipitation_mm,
        weather_code=conditions.weather_code,
        mode=mode,
        fetched_at=datetime.now(UTC),
    )


def preset_snapshot(mode: WeatherMode) -> WeatherSnapshot:
    """Return the synthetic snapshot for a manual preset."""

    return _snapshot(PRESET_CONDITIONS[mode], mode)


def fallback_snapshot() -> WeatherSnapshot:
    return _snapshot(FALLBACK_NORMAL, WeatherMode.NORMAL)


async def fetch_open_meteo(
    settings: Settings,
    client: httpx.AsyncClient | None = None,
) -> WeatherSnapshot:
    """Call Open-Meteo for the Kaluga cluster center within the 1.5 s timeout."""

    owns_client = client is None
    active_client = client or httpx.AsyncClient(timeout=settings.external_api_timeout_sec)
    try:
        response = await active_client.get(
            OPEN_METEO_URL,
            params={
                "latitude": settings.weather_latitude,
                "longitude": settings.weather_longitude,
                "current": "temperature_2m,precipitation,weather_code",
                "timezone": "UTC",
            },
        )
        response.raise_for_status()
        current = response.json()["current"]
        return WeatherSnapshot(
            temperature_c=float(current["temperature_2m"]),
            precipitation_mm=max(0.0, float(current.get("precipitation") or 0.0)),
            weather_code=current.get("weather_code"),
            mode=WeatherMode.NORMAL,
            fetched_at=datetime.now(UTC),
        )
    finally:
        if owns_client:
            await active_client.aclose()


async def get_current_weather(
    session: Session,
    settings: Settings,
    *,
    account_id: int,
    client: httpx.AsyncClient | None = None,
) -> WeatherSnapshot:
    """Return the active snapshot: preset first, then cache, then Open-Meteo."""

    mode = read_weather_mode(session, account_id=account_id)
    if mode is not WeatherMode.NORMAL:
        return preset_snapshot(mode)

    now = time.monotonic()
    cached = _cache.get(_cache_key(settings))
    if cached is not None and cached.expires_at > now:
        return cached.snapshot

    try:
        snapshot = await fetch_open_meteo(settings, client)
    except (httpx.HTTPError, KeyError, TypeError, ValueError) as error:
        logger.warning("Open-Meteo is unavailable, using fallback weather: %s", error)
        snapshot = fallback_snapshot()

    _cache[_cache_key(settings)] = _CacheEntry(
        snapshot=snapshot,
        expires_at=now + settings.weather_cache_ttl_sec,
    )
    return snapshot

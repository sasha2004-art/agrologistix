"""Mapbox distance routing with a SQLite cache and a haversine fallback.

Math contract:

* ``haversine_km`` uses the IUGG mean Earth radius ``R = 6371.0088 km`` and the
  classical haversine formula; the ``asin`` argument is clamped to ``[0, 1]``
  against floating-point drift.
* When Mapbox is unavailable, the road distance is the great-circle distance
  multiplied by the TRD detour factor ``1.3`` and the base duration assumes the
  ``60 km/h`` regional cruise speed. The solver later scales the duration with a
  concrete truck cruise speed and road surface.
* Fallback geometry is a polyline with intermediate nodes, so Mapbox GL JS can
  draw the leg without a routing response.

Geometry points are stored as ``(lat, lon)`` tuples in ``RouteCache.geojson_geometry``
to match the solver ``RoutePoint`` DTO.
"""

import asyncio
import json
import logging
import time
from dataclasses import dataclass
from math import asin, cos, radians, sin, sqrt

import httpx
from sqlmodel import Session

from app.core.config import Settings
from app.models.run_models import RouteCache

logger = logging.getLogger(__name__)

MAPBOX_DIRECTIONS_URL = "https://api.mapbox.com/directions/v5/mapbox/driving"
# IUGG mean Earth radius in kilometers.
EARTH_RADIUS_KM = 6371.0088
# Straight-line detour factor for Kaluga region roads (TRD section 4).
ROAD_FACTOR = 1.3
# Regional cruise speed used before a concrete truck is assigned (TRD section 4).
DEFAULT_SPEED_KMH = 60.0
# Number of intermediate nodes in the offline polyline.
STRAIGHT_LINE_SEGMENTS = 8
# Coordinate rounding for the cache key: five decimals are about 1.1 meters.
CACHE_PRECISION = 5
# Geometry rounding for JSON payloads: six decimals are about 0.11 meters.
GEOMETRY_PRECISION = 6
MAPBOX_SOURCE = "mapbox"
FALLBACK_SOURCE = "fallback"
# Don't retry a failed external lookup on every dashboard recalculation.
MAPBOX_RETRY_INTERVAL_SEC = 900.0


@dataclass(frozen=True, slots=True)
class Coordinate:
    lat: float
    lon: float

    def __post_init__(self) -> None:
        if not -90.0 <= self.lat <= 90.0:
            raise ValueError(f"latitude {self.lat} is outside [-90, 90]")
        if not -180.0 <= self.lon <= 180.0:
            raise ValueError(f"longitude {self.lon} is outside [-180, 180]")


@dataclass(frozen=True, slots=True)
class RouteLeg:
    """One origin -> destination leg with ``(lat, lon)`` polyline geometry."""

    distance_km: float
    base_duration_min: float
    geometry: list[tuple[float, float]]


def _normalize(value: float) -> float:
    rounded = round(value, CACHE_PRECISION)
    return 0.0 if rounded == 0 else rounded


def coordinate_key(origin: Coordinate, destination: Coordinate) -> str:
    """Deterministic ``RouteCache`` key for an ordered coordinate pair."""

    return (
        f"{_normalize(origin.lat):.5f}_{_normalize(origin.lon):.5f}"
        f"_{_normalize(destination.lat):.5f}_{_normalize(destination.lon):.5f}"
    )


def account_coordinate_key(account_id: int, origin: Coordinate, destination: Coordinate) -> str:
    return f"a{account_id}:{coordinate_key(origin, destination)}"


def haversine_km(origin: Coordinate, destination: Coordinate) -> float:
    """Great-circle distance between two coordinates in kilometers."""

    lat1, lon1, lat2, lon2 = map(
        radians,
        (origin.lat, origin.lon, destination.lat, destination.lon),
    )
    delta_lat = lat2 - lat1
    delta_lon = lon2 - lon1
    inner = sin(delta_lat / 2) ** 2 + cos(lat1) * cos(lat2) * sin(delta_lon / 2) ** 2
    # ``asin`` is undefined for arguments above 1 and floating point can overshoot.
    return 2.0 * EARTH_RADIUS_KM * asin(sqrt(min(1.0, max(0.0, inner))))


def build_polyline(
    origin: Coordinate,
    destination: Coordinate,
    segments: int = STRAIGHT_LINE_SEGMENTS,
) -> list[tuple[float, float]]:
    """Interpolated ``(lat, lon)`` polyline with intermediate nodes."""

    if segments < 1:
        raise ValueError("segments must be at least 1")

    return [
        (
            round(
                origin.lat + (destination.lat - origin.lat) * step / segments, GEOMETRY_PRECISION
            ),
            round(
                origin.lon + (destination.lon - origin.lon) * step / segments, GEOMETRY_PRECISION
            ),
        )
        for step in range(segments + 1)
    ]


def fallback_leg(
    origin: Coordinate,
    destination: Coordinate,
    speed_kmh: float = DEFAULT_SPEED_KMH,
) -> RouteLeg:
    """Instant road estimate used when no external routing is available."""

    distance_km = haversine_km(origin, destination) * ROAD_FACTOR
    duration_min = distance_km / speed_kmh * 60.0
    return RouteLeg(
        distance_km=round(distance_km, 3),
        base_duration_min=round(duration_min, 3),
        geometry=build_polyline(origin, destination),
    )


def _mapbox_token(settings: Settings) -> str:
    return settings.mapbox_secret_token.get_secret_value().strip()


async def fetch_mapbox_leg(
    origin: Coordinate,
    destination: Coordinate,
    settings: Settings,
    client: httpx.AsyncClient | None = None,
) -> RouteLeg | None:
    """Request a real road route from Mapbox Directions, or ``None`` on failure."""

    token = _mapbox_token(settings)
    if not token:
        return None

    owns_client = client is None
    active_client = client or httpx.AsyncClient(timeout=settings.mapbox_timeout_sec)
    coordinates = f"{origin.lon},{origin.lat};{destination.lon},{destination.lat}"
    try:
        response = await active_client.get(
            f"{MAPBOX_DIRECTIONS_URL}/{coordinates}",
            params={"geometries": "geojson", "overview": "full", "access_token": token},
        )
        response.raise_for_status()
        route = response.json()["routes"][0]
        route_distance_km = float(route["distance"]) / 1000.0
        route_duration_min = float(route["duration"]) / 60.0
        geometry = [
            (round(float(lat), GEOMETRY_PRECISION), round(float(lon), GEOMETRY_PRECISION))
            for lon, lat in route["geometry"]["coordinates"]
        ]
        if len(geometry) < 2:
            raise ValueError("Mapbox Directions returned no usable road geometry")
        return RouteLeg(
            distance_km=round(route_distance_km, 3),
            base_duration_min=round(route_duration_min, 3),
            geometry=geometry,
        )
    except (httpx.HTTPError, KeyError, IndexError, TypeError, ValueError) as error:
        logger.warning("Mapbox Directions is unavailable, using haversine fallback: %s", error)
        return None
    finally:
        if owns_client:
            await active_client.aclose()


def _cached_leg(entry: RouteCache, origin: Coordinate, destination: Coordinate) -> RouteLeg:
    fallback_geometry = build_polyline(origin, destination)
    geometry = fallback_geometry
    if entry.geojson_geometry:
        try:
            geometry = [(float(lat), float(lon)) for lat, lon in json.loads(entry.geojson_geometry)]
        except (TypeError, ValueError):
            geometry = fallback_geometry
    return RouteLeg(
        distance_km=entry.distance_km,
        base_duration_min=entry.base_duration_min,
        geometry=geometry,
    )


def _should_refresh_fallback(entry: RouteCache, has_mapbox_token: bool, now: float) -> bool:
    """Upgrade old fallback geometry once Mapbox is enabled; throttle failures."""

    if not has_mapbox_token or entry.source == MAPBOX_SOURCE:
        return False
    return (
        entry.mapbox_checked_at is None
        or now - entry.mapbox_checked_at >= MAPBOX_RETRY_INTERVAL_SEC
    )


def _persist_leg(
    session: Session,
    account_id: int,
    pair_key: str,
    leg: RouteLeg,
    source: str,
    mapbox_checked_at: float | None,
    cached: RouteCache | None = None,
) -> None:
    """Insert or update one cached route and its provider metadata."""

    entry = cached or RouteCache(
        pair_key=pair_key,
        account_id=account_id,
        distance_km=leg.distance_km,
        base_duration_min=leg.base_duration_min,
    )
    entry.distance_km = leg.distance_km
    entry.base_duration_min = leg.base_duration_min
    entry.geojson_geometry = json.dumps(leg.geometry)
    entry.source = source
    entry.mapbox_checked_at = mapbox_checked_at
    session.add(entry)


async def get_route_leg(
    session: Session,
    origin: Coordinate,
    destination: Coordinate,
    settings: Settings,
    *,
    account_id: int,
    client: httpx.AsyncClient | None = None,
) -> RouteLeg:
    """Return a road leg, refreshing old fallback entries when Mapbox is enabled."""

    pair_key = account_coordinate_key(account_id, origin, destination)
    cached = session.get(RouteCache, pair_key)
    if cached is not None and cached.account_id != account_id:
        cached = None
    token_available = bool(_mapbox_token(settings))
    now = time.time()
    if cached is not None and not _should_refresh_fallback(cached, token_available, now):
        return _cached_leg(cached, origin, destination)

    leg = await fetch_mapbox_leg(origin, destination, settings, client)
    source = MAPBOX_SOURCE if leg is not None else FALLBACK_SOURCE
    checked_at = now if token_available else None
    if leg is None:
        leg = fallback_leg(origin, destination)

    _persist_leg(session, account_id, pair_key, leg, source, checked_at, cached)
    session.commit()
    return leg


async def build_distance_matrix(
    session: Session,
    points: list[Coordinate],
    settings: Settings,
    *,
    account_id: int,
    client: httpx.AsyncClient | None = None,
) -> list[list[RouteLeg]]:
    """Build an NxN matrix with concurrent fetches and a shared API deadline."""

    pairs = {
        account_coordinate_key(account_id, origin, destination): (origin, destination)
        for row, origin in enumerate(points)
        for column, destination in enumerate(points)
        if row != column
    }
    resolved: dict[str, RouteLeg] = {}
    missing: dict[str, tuple[Coordinate, Coordinate]] = {}
    cached_entries: dict[str, RouteCache | None] = {}
    token_available = bool(_mapbox_token(settings))
    now = time.time()
    for key, (origin, destination) in pairs.items():
        cached = session.get(RouteCache, key)
        if cached is not None and cached.account_id != account_id:
            cached = None
        if cached is None or _should_refresh_fallback(cached, token_available, now):
            missing[key] = (origin, destination)
            cached_entries[key] = cached
        else:
            resolved[key] = _cached_leg(cached, origin, destination)

    owns_client = client is None
    active_client = client
    if owns_client and _mapbox_token(settings):
        active_client = httpx.AsyncClient(timeout=settings.mapbox_timeout_sec)
    mapbox_successes: set[str] = set()
    try:
        semaphore = asyncio.Semaphore(8)

        async def fetch_pair(
            key: str, origin: Coordinate, destination: Coordinate
        ) -> tuple[str, RouteLeg | None]:
            async with semaphore:
                leg = await fetch_mapbox_leg(origin, destination, settings, active_client)
            return key, leg

        attempt_started_at = now
        if missing and token_available:
            try:
                async with asyncio.timeout(settings.mapbox_timeout_sec):
                    fetched = await asyncio.gather(
                        *(fetch_pair(key, *pair) for key, pair in missing.items())
                    )
                for key, leg in fetched:
                    if leg is not None:
                        resolved[key] = leg
                        mapbox_successes.add(key)
            except TimeoutError:
                logger.warning("Mapbox matrix deadline exceeded, using fallback legs")

        for key, (origin, destination) in missing.items():
            leg = resolved.get(key) or fallback_leg(origin, destination)
            resolved[key] = leg
            source = MAPBOX_SOURCE if key in mapbox_successes else FALLBACK_SOURCE
            checked_at = attempt_started_at if token_available else None
            _persist_leg(
                session,
                account_id,
                key,
                leg,
                source,
                checked_at,
                cached_entries.get(key),
            )
        if missing:
            session.commit()
    finally:
        if owns_client and active_client is not None:
            await active_client.aclose()

    return [
        [
            RouteLeg(0.0, 0.0, [(origin.lat, origin.lon)])
            if row == column
            else resolved[account_coordinate_key(account_id, origin, destination)]
            for column, destination in enumerate(points)
        ]
        for row, origin in enumerate(points)
    ]

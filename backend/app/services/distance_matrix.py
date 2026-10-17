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
    active_client = client or httpx.AsyncClient(timeout=settings.external_api_timeout_sec)
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


async def get_route_leg(
    session: Session,
    origin: Coordinate,
    destination: Coordinate,
    settings: Settings,
    client: httpx.AsyncClient | None = None,
) -> RouteLeg:
    """Return a cached leg, otherwise resolve it via Mapbox or the fallback."""

    pair_key = coordinate_key(origin, destination)
    cached = session.get(RouteCache, pair_key)
    if cached is not None:
        return _cached_leg(cached, origin, destination)

    leg = await fetch_mapbox_leg(origin, destination, settings, client)
    if leg is None:
        leg = fallback_leg(origin, destination)

    session.add(
        RouteCache(
            pair_key=pair_key,
            distance_km=leg.distance_km,
            base_duration_min=leg.base_duration_min,
            geojson_geometry=json.dumps(leg.geometry),
        )
    )
    session.commit()
    return leg


async def build_distance_matrix(
    session: Session,
    points: list[Coordinate],
    settings: Settings,
    client: httpx.AsyncClient | None = None,
) -> list[list[RouteLeg]]:
    """Build an NxN matrix with concurrent fetches and a shared API deadline."""

    pairs = {
        coordinate_key(origin, destination): (origin, destination)
        for row, origin in enumerate(points)
        for column, destination in enumerate(points)
        if row != column
    }
    resolved: dict[str, RouteLeg] = {}
    missing: dict[str, tuple[Coordinate, Coordinate]] = {}
    for key, (origin, destination) in pairs.items():
        cached = session.get(RouteCache, key)
        if cached is None:
            missing[key] = (origin, destination)
        else:
            resolved[key] = _cached_leg(cached, origin, destination)

    owns_client = client is None
    active_client = client
    if owns_client and _mapbox_token(settings):
        active_client = httpx.AsyncClient(timeout=settings.external_api_timeout_sec)
    try:
        semaphore = asyncio.Semaphore(8)

        async def fetch_pair(
            key: str, origin: Coordinate, destination: Coordinate
        ) -> tuple[str, RouteLeg | None]:
            async with semaphore:
                leg = await fetch_mapbox_leg(origin, destination, settings, active_client)
            return key, leg

        if missing and _mapbox_token(settings):
            try:
                async with asyncio.timeout(settings.external_api_timeout_sec):
                    fetched = await asyncio.gather(
                        *(fetch_pair(key, *pair) for key, pair in missing.items())
                    )
                resolved.update({key: leg for key, leg in fetched if leg is not None})
            except TimeoutError:
                logger.warning("Mapbox matrix deadline exceeded, using fallback legs")

        for key, (origin, destination) in missing.items():
            leg = resolved.get(key) or fallback_leg(origin, destination)
            resolved[key] = leg
            session.add(
                RouteCache(
                    pair_key=key,
                    distance_km=leg.distance_km,
                    base_duration_min=leg.base_duration_min,
                    geojson_geometry=json.dumps(leg.geometry),
                )
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
            else resolved[coordinate_key(origin, destination)]
            for column, destination in enumerate(points)
        ]
        for row, origin in enumerate(points)
    ]

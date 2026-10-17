import asyncio
import time
from math import pi

import httpx
import pytest
from app.core.config import Settings
from app.models.run_models import RouteCache
from app.services import distance_matrix as dm
from sqlmodel import Session, select

OBININSK = dm.Coordinate(lat=55.0968, lon=36.6103)
KALUGA = dm.Coordinate(lat=54.5138, lon=36.2612)
MALOYAROSLAVETS = dm.Coordinate(lat=55.0147, lon=36.4719)


def _settings(token: str = "") -> Settings:
    return Settings(sqlite_db_path=":memory:", mapbox_secret_token=token)


def test_haversine_one_degree_on_equator_and_meridian() -> None:
    equator = dm.haversine_km(dm.Coordinate(0.0, 0.0), dm.Coordinate(0.0, 1.0))
    meridian = dm.haversine_km(dm.Coordinate(0.0, 0.0), dm.Coordinate(1.0, 0.0))
    expected = dm.EARTH_RADIUS_KM * pi / 180.0

    assert equator == pytest.approx(expected, abs=1e-6)
    assert meridian == pytest.approx(expected, abs=1e-6)


def test_haversine_pole_to_pole_is_half_circumference() -> None:
    distance = dm.haversine_km(dm.Coordinate(90.0, 0.0), dm.Coordinate(-90.0, 0.0))

    assert distance == pytest.approx(pi * dm.EARTH_RADIUS_KM, abs=1e-6)


def test_haversine_is_symmetric() -> None:
    forward = dm.haversine_km(OBININSK, MALOYAROSLAVETS)
    backward = dm.haversine_km(MALOYAROSLAVETS, OBININSK)

    assert forward == pytest.approx(backward, rel=1e-12)


def test_haversine_known_kaluga_distances() -> None:
    obninsk_kaluga = dm.haversine_km(OBININSK, KALUGA)
    obninsk_maloyaroslavets = dm.haversine_km(OBININSK, MALOYAROSLAVETS)

    assert obninsk_kaluga == pytest.approx(68.579, abs=0.5)
    assert obninsk_maloyaroslavets == pytest.approx(12.690, abs=0.2)


def test_haversine_identical_points_is_zero() -> None:
    assert dm.haversine_km(OBININSK, OBININSK) == 0.0


def test_coordinate_construction_fails_for_out_of_range() -> None:
    with pytest.raises(ValueError):
        dm.Coordinate(lat=95.0, lon=36.0)
    with pytest.raises(ValueError):
        dm.Coordinate(lat=55.0, lon=-200.0)


def test_fallback_applies_road_factor_and_cruise_speed() -> None:
    leg = dm.fallback_leg(OBININSK, KALUGA)
    straight = dm.haversine_km(OBININSK, KALUGA)
    expected_distance = round(straight * dm.ROAD_FACTOR, 3)

    assert expected_distance == pytest.approx(89.152, abs=0.05)
    assert leg.distance_km == expected_distance
    assert leg.base_duration_min == pytest.approx(expected_distance, rel=1e-6)


def test_polyline_has_intermediate_nodes() -> None:
    geometry = dm.build_polyline(OBININSK, KALUGA, segments=8)

    assert len(geometry) == 9
    assert geometry[0] == pytest.approx((OBININSK.lat, OBININSK.lon))
    assert geometry[-1] == pytest.approx((KALUGA.lat, KALUGA.lon))
    midpoint = geometry[4]
    assert midpoint[0] == pytest.approx((OBININSK.lat + KALUGA.lat) / 2)
    assert midpoint[1] == pytest.approx((OBININSK.lon + KALUGA.lon) / 2)


def test_polyline_requires_at_least_one_segment() -> None:
    with pytest.raises(ValueError):
        dm.build_polyline(OBININSK, KALUGA, segments=0)


def test_coordinate_key_is_stable_and_directional() -> None:
    forward = dm.coordinate_key(OBININSK, KALUGA)
    backward = dm.coordinate_key(KALUGA, OBININSK)

    assert forward == dm.coordinate_key(OBININSK, KALUGA)
    assert forward != backward
    assert len(forward.split("_")) == 4
    assert forward == "55.09680_36.61030_54.51380_36.26120"


def test_coordinate_key_normalizes_negative_zero() -> None:
    assert dm.coordinate_key(dm.Coordinate(0.0, 0.0), dm.Coordinate(0.0, 0.0)) == (
        "0.00000_0.00000_0.00000_0.00000"
    )


def test_route_leg_is_cached_in_sqlite(session: Session) -> None:
    leg = asyncio.run(dm.get_route_leg(session, OBININSK, KALUGA, _settings()))

    stored = session.exec(select(RouteCache)).all()
    assert leg.distance_km == pytest.approx(89.152, abs=0.05)
    assert len(stored) == 1
    assert stored[0].pair_key == dm.coordinate_key(OBININSK, KALUGA)
    assert stored[0].distance_km == leg.distance_km


def test_second_call_uses_cache_without_network(
    session: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    first = asyncio.run(dm.get_route_leg(session, OBININSK, KALUGA, _settings()))

    async def forbidden(*args: object, **kwargs: object) -> dm.RouteLeg:
        raise AssertionError("Mapbox must not be called for a cached leg")

    monkeypatch.setattr(dm, "fetch_mapbox_leg", forbidden)
    second = asyncio.run(dm.get_route_leg(session, OBININSK, KALUGA, _settings()))

    assert second.distance_km == first.distance_km
    assert second.geometry == first.geometry


def test_mapbox_leg_is_preferred_when_available(
    session: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    geometry = dm.build_polyline(OBININSK, KALUGA, segments=2)

    async def fake_mapbox(*args: object, **kwargs: object) -> dm.RouteLeg:
        return dm.RouteLeg(distance_km=100.0, base_duration_min=80.0, geometry=geometry)

    monkeypatch.setattr(dm, "fetch_mapbox_leg", fake_mapbox)
    leg = asyncio.run(dm.get_route_leg(session, OBININSK, KALUGA, _settings("pk.test")))

    assert leg.distance_km == 100.0
    stored = session.get(RouteCache, dm.coordinate_key(OBININSK, KALUGA))
    assert stored is not None
    assert stored.distance_km == 100.0


def test_empty_token_skips_network_instantly() -> None:
    started = time.perf_counter()
    leg = asyncio.run(dm.fetch_mapbox_leg(OBININSK, KALUGA, _settings()))

    assert leg is None
    assert time.perf_counter() - started < 0.1


def test_mapbox_response_is_parsed_and_lon_lat_order_is_flipped() -> None:
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "routes": [
                    {
                        "distance": 12345.6,
                        "duration": 900.0,
                        "geometry": {"coordinates": [[36.6103, 55.0968], [36.2612, 54.5138]]},
                    }
                ]
            },
        )

    async def run() -> dm.RouteLeg | None:
        transport = httpx.MockTransport(handler)
        async with httpx.AsyncClient(transport=transport) as client:
            return await dm.fetch_mapbox_leg(OBININSK, KALUGA, _settings("pk.test"), client)

    leg = asyncio.run(run())

    assert leg is not None
    assert leg.distance_km == 12.346
    assert leg.base_duration_min == 15.0
    assert leg.geometry == [(55.0968, 36.6103), (54.5138, 36.2612)]


def test_mapbox_http_error_falls_back_to_none() -> None:
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, json={"message": "boom"})

    async def run() -> dm.RouteLeg | None:
        transport = httpx.MockTransport(handler)
        async with httpx.AsyncClient(transport=transport) as client:
            return await dm.fetch_mapbox_leg(OBININSK, KALUGA, _settings("pk.test"), client)

    assert asyncio.run(run()) is None


def test_corrupted_cache_geometry_falls_back_to_polyline(session: Session) -> None:
    session.add(
        RouteCache(
            pair_key=dm.coordinate_key(OBININSK, KALUGA),
            distance_km=89.152,
            base_duration_min=89.152,
            geojson_geometry="{not-json",
        )
    )
    session.commit()

    leg = asyncio.run(dm.get_route_leg(session, OBININSK, KALUGA, _settings()))

    assert leg.distance_km == 89.152
    assert len(leg.geometry) == dm.STRAIGHT_LINE_SEGMENTS + 1


def test_matrix_for_seven_points_uses_cache_on_second_run(session: Session) -> None:
    points = [
        dm.Coordinate(lat=55.0968, lon=36.6103),
        dm.Coordinate(lat=54.5138, lon=36.2612),
        dm.Coordinate(lat=55.0147, lon=36.4719),
        dm.Coordinate(lat=55.2075, lon=36.4850),
        dm.Coordinate(lat=55.1797, lon=36.6597),
        dm.Coordinate(lat=54.7200, lon=37.1800),
        dm.Coordinate(lat=54.8083, lon=36.2333),
    ]
    settings = _settings()

    started = time.perf_counter()
    first_matrix = asyncio.run(dm.build_distance_matrix(session, points, settings))
    first_elapsed = time.perf_counter() - started

    started = time.perf_counter()
    second_matrix = asyncio.run(dm.build_distance_matrix(session, points, settings))
    second_elapsed = time.perf_counter() - started

    assert len(first_matrix) == 7
    assert all(len(row) == 7 for row in first_matrix)
    assert all(first_matrix[index][index].distance_km == 0.0 for index in range(7))
    assert len(session.exec(select(RouteCache)).all()) == 7 * 6
    assert second_matrix[1][2].distance_km == first_matrix[1][2].distance_km
    assert first_elapsed < 1.0
    assert second_elapsed < 0.1


def test_fetch_closes_its_own_http_client(monkeypatch: pytest.MonkeyPatch) -> None:
    closed: list[bool] = []

    class _FakeClient:
        def __init__(self, *_args: object, **_kwargs: object) -> None:
            pass

        async def get(self, *_args: object, **_kwargs: object) -> httpx.Response:
            request = httpx.Request("GET", "https://api.mapbox.com/directions/v5")
            return httpx.Response(
                200,
                json={
                    "routes": [
                        {
                            "distance": 1000.0,
                            "duration": 60.0,
                            "geometry": {"coordinates": []},
                        }
                    ]
                },
                request=request,
            )

        async def aclose(self) -> None:
            closed.append(True)

    monkeypatch.setattr(dm.httpx, "AsyncClient", _FakeClient)

    leg = asyncio.run(dm.fetch_mapbox_leg(OBININSK, KALUGA, _settings("pk.test")))

    assert closed == [True]
    assert leg is not None
    assert leg.distance_km == 1.0
    assert leg.geometry == []


def test_matrix_is_symmetric_for_straight_line_fallback(session: Session) -> None:
    points = [OBININSK, KALUGA, MALOYAROSLAVETS]

    matrix = asyncio.run(dm.build_distance_matrix(session, points, _settings()))

    assert matrix[0][1].distance_km == matrix[1][0].distance_km
    assert matrix[0][2].base_duration_min == pytest.approx(matrix[2][0].base_duration_min)


def test_cold_matrix_fetches_mapbox_legs_concurrently(
    session: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    points = [
        dm.Coordinate(lat=55.0968, lon=36.6103),
        dm.Coordinate(lat=54.5138, lon=36.2612),
        dm.Coordinate(lat=55.0147, lon=36.4719),
        dm.Coordinate(lat=55.2075, lon=36.4850),
        dm.Coordinate(lat=55.1797, lon=36.6597),
    ]
    calls = 0

    async def slow_mapbox(origin: object, destination: object, *args: object, **kwargs: object):
        nonlocal calls
        calls += 1
        await asyncio.sleep(0.05)
        return dm.fallback_leg(origin, destination)  # type: ignore[arg-type]

    monkeypatch.setattr(dm, "fetch_mapbox_leg", slow_mapbox)
    settings = Settings(
        sqlite_db_path=":memory:",
        mapbox_secret_token="pk.test",
        external_api_timeout_sec=5.0,
    )

    started = time.perf_counter()
    matrix = asyncio.run(dm.build_distance_matrix(session, points, settings))
    elapsed = time.perf_counter() - started

    assert calls == 20
    assert len(matrix) == 5
    assert elapsed < 0.6


def test_matrix_falls_back_when_mapbox_exceeds_the_deadline(
    session: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    points = [OBININSK, KALUGA, MALOYAROSLAVETS]

    async def stalled_mapbox(*args: object, **kwargs: object) -> dm.RouteLeg:
        await asyncio.sleep(5.0)
        raise AssertionError("the deadline must cancel this coroutine")

    monkeypatch.setattr(dm, "fetch_mapbox_leg", stalled_mapbox)
    settings = Settings(
        sqlite_db_path=":memory:",
        mapbox_secret_token="pk.test",
        external_api_timeout_sec=0.2,
    )

    started = time.perf_counter()
    matrix = asyncio.run(dm.build_distance_matrix(session, points, settings))
    elapsed = time.perf_counter() - started

    assert elapsed < 1.0
    assert all(len(row) == 3 for row in matrix)
    assert matrix[0][1].distance_km == pytest.approx(dm.fallback_leg(OBININSK, KALUGA).distance_km)
    assert len(session.exec(select(RouteCache)).all()) == 6

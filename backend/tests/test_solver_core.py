"""Routing math tests: 2-opt ordering, ETA, freshness and geometry."""

from itertools import permutations
from math import exp

import pytest
from app.schemas.enums import RoadType
from app.services.distance_matrix import Coordinate, fallback_leg
from app.services.solver_engine import SolverWeather, run_solver
from app.services.solver_routing import LegIndex, two_opt_order
from tests.solver_factory import (
    BALABANOVO,
    BOROVSK,
    DETCHINO,
    KALUGA,
    OBININSK,
    _make_input,
    _order,
    _point_legs,
    _stock,
    _truck,
)


def test_single_stop_eta_and_freshness_match_the_formula() -> None:
    solver_input = _make_input(
        orders=[_order(1, kg=1000.0, point=KALUGA)],
        trucks=[_truck(1, speed=60.0, reefer=True)],
    )

    outcome = run_solver(solver_input)
    route = outcome.routes[0]
    stop = route.stops[0]

    distance = fallback_leg(
        Coordinate(lat=OBININSK[0], lon=OBININSK[1]),
        Coordinate(lat=KALUGA[0], lon=KALUGA[1]),
    ).distance_km
    expected_hours = distance / 60.0
    expected_freshness = exp(-0.08 * expected_hours)

    assert stop.distance_km == pytest.approx(distance, abs=0.01)
    assert stop.eta_minutes == pytest.approx(expected_hours * 60.0, rel=1e-3)
    assert stop.expected_freshness == pytest.approx(expected_freshness, rel=1e-4)


def test_dirt_approach_is_slower_in_eta() -> None:
    asphalt_input = _make_input(
        orders=[_order(1, road_type=RoadType.ASPHALT, point=BOROVSK)],
        trucks=[_truck(1)],
    )
    dirt_input = _make_input(
        orders=[_order(1, road_type=RoadType.DIRT, point=BOROVSK)],
        trucks=[_truck(1)],
    )

    asphalt_eta = run_solver(asphalt_input).routes[0].stops[0].eta_minutes
    dirt_eta = run_solver(dirt_input).routes[0].stops[0].eta_minutes

    assert dirt_eta == pytest.approx(asphalt_eta * 1.35, rel=1e-3)


def test_rain_slows_the_route_down() -> None:
    dry = _make_input(
        orders=[_order(1, point=BOROVSK)],
        trucks=[_truck(1)],
    )
    wet = _make_input(
        orders=[_order(1, point=BOROVSK)],
        trucks=[_truck(1)],
        weather=SolverWeather(temperature_c=14.0, precipitation_mm=12.0, mode="heavy_rain"),
    )

    dry_eta = run_solver(dry).routes[0].stops[0].eta_minutes
    wet_eta = run_solver(wet).routes[0].stops[0].eta_minutes

    assert wet_eta == pytest.approx(dry_eta * 1.3, rel=1e-3)


def test_geometry_starts_at_warehouse_and_covers_stops() -> None:
    solver_input = _make_input(
        orders=[_order(1, point=BOROVSK), _order(2, client_id=2, point=BALABANOVO)],
        trucks=[_truck(1)],
    )

    outcome = run_solver(solver_input)
    route = outcome.routes[0]

    assert route.geometry[0] == pytest.approx(OBININSK)
    assert len(route.geometry) >= len(route.stops) + 1
    for point in (BOROVSK, BALABANOVO):
        assert any(
            abs(lat - point[0]) < 1e-6 and abs(lon - point[1]) < 1e-6 for lat, lon in route.geometry
        )


def test_two_opt_beats_naive_permutations() -> None:
    points = [KALUGA, BOROVSK, BALABANOVO]
    index = LegIndex(_point_legs([OBININSK, *points]))

    order = two_opt_order(OBININSK, points, list(range(len(points))), index.distance_km)
    ordered = [points[position] for position in order]

    def route_length(sequence: list[tuple[float, float]]) -> float:
        total = 0.0
        previous = OBININSK
        for point in sequence:
            total += index.distance_km(previous, point)
            previous = point
        return total

    best_permutation = min(route_length(list(order)) for order in permutations(points))
    assert route_length(ordered) <= best_permutation + 1e-6


def test_two_opt_order_distance_never_grows() -> None:
    points = [BOROVSK, KALUGA, BALABANOVO, DETCHINO]
    index = LegIndex(_point_legs([OBININSK, *points]))

    initial = list(points)
    improved_order = two_opt_order(
        OBININSK,
        initial,
        list(range(len(initial))),
        index.distance_km,
    )
    improved = [initial[position] for position in improved_order]

    def route_length(sequence: list[tuple[float, float]]) -> float:
        total = 0.0
        previous = OBININSK
        for point in sequence:
            total += index.distance_km(previous, point)
            previous = point
        return total

    assert route_length(improved) <= route_length(initial) + 1e-9


def test_initial_freshness_from_stock_is_applied() -> None:
    fresh_input = _make_input(
        orders=[_order(1)],
        trucks=[_truck(1)],
        stocks=[_stock(freshness=1.0)],
    )
    stale_input = _make_input(
        orders=[_order(1)],
        trucks=[_truck(1)],
        stocks=[_stock(freshness=0.8)],
    )

    fresh_stop = run_solver(fresh_input).routes[0].stops[0]
    stale_stop = run_solver(stale_input).routes[0].stops[0]

    assert stale_stop.expected_freshness < fresh_stop.expected_freshness
    assert stale_stop.expected_freshness == pytest.approx(
        fresh_stop.expected_freshness * 0.8,
        rel=1e-6,
    )

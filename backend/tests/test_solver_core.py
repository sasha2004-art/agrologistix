"""Hard-constraint tests for the Day 7 solver core."""

import asyncio
from itertools import permutations
from math import exp

import pytest
from app.schemas.enums import RoadType, TruckStatus, WarningSeverity
from app.services.distance_matrix import Coordinate, fallback_leg
from app.services.solver_engine import (
    SolverInput,
    SolverLeg,
    SolverOrder,
    SolverProduct,
    SolverStock,
    SolverTruck,
    SolverWarehouse,
    SolverWeather,
    run_solver,
    solve_async,
)
from app.services.solver_routing import LegIndex, two_opt_order

OBININSK = (55.0968, 36.6103)
DETCHINO = (54.8083, 36.2333)
KALUGA = (54.5138, 36.2612)
BOROVSK = (55.2075, 36.4850)
BALABANOVO = (55.1797, 36.6597)


def _leg(origin: tuple[float, float], destination: tuple[float, float]) -> SolverLeg:
    fallback = fallback_leg(
        Coordinate(lat=origin[0], lon=origin[1]),
        Coordinate(lat=destination[0], lon=destination[1]),
    )
    return SolverLeg(
        origin=origin,
        destination=destination,
        distance_km=fallback.distance_km,
        base_duration_min=fallback.base_duration_min,
        geometry=tuple(fallback.geometry),
    )


def _point_legs(points: list[tuple[float, float]]) -> tuple:
    return tuple(
        _leg(origin, destination)
        for origin in points
        for destination in points
        if origin != destination
    )


def _warehouse(warehouse_id: int = 1, point: tuple[float, float] = OBININSK) -> SolverWarehouse:
    return SolverWarehouse(
        warehouse_id=warehouse_id,
        name=f"Склад {warehouse_id}",
        latitude=point[0],
        longitude=point[1],
    )


def _order(
    order_id: int = 1,
    *,
    client_id: int = 1,
    product_id: int = 1,
    kg: float = 1000.0,
    price: float = 300.0,
    penalty: float = 100.0,
    road_type: RoadType = RoadType.ASPHALT,
    point: tuple[float, float] = KALUGA,
) -> SolverOrder:
    return SolverOrder(
        order_id=order_id,
        client_id=client_id,
        product_id=product_id,
        requested_kg=kg,
        price_per_kg=price,
        penalty_per_kg=penalty,
        road_type=road_type,
        latitude=point[0],
        longitude=point[1],
    )


def _truck(
    truck_id: int = 1,
    *,
    warehouse_id: int = 1,
    capacity: float = 10_000.0,
    speed: float = 60.0,
    cost_km: float = 30.0,
    fixed: float = 3000.0,
    reefer: bool = True,
    dirt: bool = True,
    status: TruckStatus = TruckStatus.ACTIVE,
) -> SolverTruck:
    return SolverTruck(
        truck_id=truck_id,
        name=f"Машина {truck_id}",
        warehouse_id=warehouse_id,
        capacity_kg=capacity,
        cruise_speed_kmh=speed,
        cost_per_km_rub=cost_km,
        fixed_trip_cost_rub=fixed,
        has_reefer=reefer,
        can_use_dirt=dirt,
        status=status,
    )


def _stock(
    warehouse_id: int = 1,
    product_id: int = 1,
    kg: float = 10_000.0,
    freshness: float = 1.0,
) -> SolverStock:
    return SolverStock(
        warehouse_id=warehouse_id,
        product_id=product_id,
        available_kg=kg,
        initial_freshness=freshness,
    )


def _make_input(
    *,
    orders: list[SolverOrder],
    trucks: list[SolverTruck],
    stocks: list[SolverStock] | None = None,
    warehouses: list[SolverWarehouse] | None = None,
    weather: SolverWeather | None = None,
    frozen: tuple[int, ...] = (),
) -> SolverInput:
    warehouse_list = warehouses or [_warehouse()]
    points = [(warehouse.latitude, warehouse.longitude) for warehouse in warehouse_list] + [
        (order.latitude, order.longitude) for order in orders
    ]
    return SolverInput(
        products=(SolverProduct(product_id=1, spoilage_rate=0.08, base_cost_rub=180.0),),
        stocks=tuple(stocks if stocks is not None else [_stock()]),
        orders=tuple(orders),
        trucks=tuple(trucks),
        legs=_point_legs(points),
        weather=weather or SolverWeather(temperature_c=20.0, precipitation_mm=0.0, mode="normal"),
        warehouses=tuple(warehouse_list),
        frozen_order_ids=frozen,
    )


def test_capacity_constraint_limits_shipped_weight() -> None:
    solver_input = _make_input(
        orders=[_order(1, kg=800.0), _order(2, client_id=2, kg=800.0, point=BOROVSK)],
        trucks=[_truck(capacity=1000.0)],
    )

    outcome = run_solver(solver_input)

    assert sum(stop.shipped_kg for route in outcome.routes for stop in route.stops) <= 1000.0
    assert outcome.metrics.shipped_kg <= 1000.0
    assert outcome.metrics.unmet_kg == pytest.approx(600.0, abs=0.01)


def test_multiple_trucks_split_capacity() -> None:
    solver_input = _make_input(
        orders=[_order(1, kg=900.0), _order(2, client_id=2, kg=900.0, point=BALABANOVO)],
        trucks=[_truck(1, capacity=1000.0), _truck(2, capacity=1000.0)],
    )

    outcome = run_solver(solver_input)

    assert outcome.metrics.shipped_kg == pytest.approx(1800.0, abs=0.01)
    assert outcome.metrics.unmet_kg == pytest.approx(0.0, abs=0.01)
    for route in outcome.routes:
        assert sum(stop.shipped_kg for stop in route.stops) <= 1000.0 + 1e-6


def test_warehouse_stock_constraint() -> None:
    solver_input = _make_input(
        orders=[_order(1, kg=900.0)],
        trucks=[_truck(capacity=5000.0)],
        stocks=[_stock(kg=500.0)],
    )

    outcome = run_solver(solver_input)

    assert outcome.metrics.shipped_kg == pytest.approx(500.0, abs=0.01)
    assert outcome.metrics.unmet_kg == pytest.approx(400.0, abs=0.01)


def test_stock_constraint_is_per_warehouse_and_product() -> None:
    solver_input = _make_input(
        orders=[_order(1, kg=600.0, product_id=1)],
        trucks=[_truck(1, warehouse_id=2, capacity=5000.0)],
        stocks=[_stock(warehouse_id=1, product_id=1, kg=5000.0)],
        warehouses=[_warehouse(1), _warehouse(2, DETCHINO)],
    )

    outcome = run_solver(solver_input)

    assert outcome.metrics.shipped_kg == 0.0
    assert outcome.metrics.unmet_kg == pytest.approx(600.0, abs=0.01)


def test_dirt_order_never_gets_a_heavy_truck() -> None:
    solver_input = _make_input(
        orders=[_order(1, road_type=RoadType.DIRT, point=BOROVSK)],
        trucks=[_truck(1, dirt=False)],
    )

    outcome = run_solver(solver_input)

    assert outcome.routes == ()
    assert outcome.metrics.unmet_kg == pytest.approx(1000.0, abs=0.01)
    codes = {warning.code for warning in outcome.warnings}
    assert "dirt_unreachable" in codes
    dirt_warning = next(w for w in outcome.warnings if w.code == "dirt_unreachable")
    assert dirt_warning.severity == WarningSeverity.ERROR.value


def test_dirt_order_is_served_by_offroad_truck() -> None:
    solver_input = _make_input(
        orders=[_order(1, road_type=RoadType.DIRT, point=BOROVSK)],
        trucks=[_truck(1, dirt=False), _truck(2, dirt=True, capacity=6000.0)],
    )

    outcome = run_solver(solver_input)

    assert outcome.metrics.shipped_kg == pytest.approx(1000.0, abs=0.01)
    assert {route.truck_id for route in outcome.routes} == {2}


def test_broken_truck_is_never_used() -> None:
    solver_input = _make_input(
        orders=[_order(1)],
        trucks=[
            _truck(1, status=TruckStatus.BROKEN),
            _truck(2, capacity=6000.0),
        ],
    )

    outcome = run_solver(solver_input)

    assert {route.truck_id for route in outcome.routes} == {2}
    assert "broken_trucks_excluded" in {warning.code for warning in outcome.warnings}


def test_all_trucks_broken_is_still_feasible() -> None:
    solver_input = _make_input(
        orders=[_order(1, kg=1200.0)],
        trucks=[_truck(1, status=TruckStatus.BROKEN)],
    )

    outcome = run_solver(solver_input)

    assert outcome.routes == ()
    assert outcome.metrics.shipped_kg == 0.0
    assert outcome.metrics.unmet_kg == pytest.approx(1200.0, abs=0.01)
    assert outcome.metrics.total_tco_rub == pytest.approx(1200.0 * 100.0, abs=0.01)
    assert outcome.metrics.avg_freshness_pct == 0.0
    codes = {warning.code for warning in outcome.warnings}
    assert {"no_active_trucks", "unmet_demand"} <= codes


def test_frozen_orders_are_not_reassigned() -> None:
    solver_input = _make_input(
        orders=[_order(1, kg=500.0), _order(2, client_id=2, kg=700.0, point=BOROVSK)],
        trucks=[_truck(capacity=10_000.0)],
        frozen=(1,),
    )

    outcome = run_solver(solver_input)

    shipped_order_ids = {stop.order_id for route in outcome.routes for stop in route.stops}
    assert shipped_order_ids == {2}
    assert outcome.metrics.unmet_kg == 0.0
    assert outcome.metrics.shipped_kg == pytest.approx(700.0, abs=0.01)


def test_metrics_are_internally_consistent() -> None:
    solver_input = _make_input(
        orders=[_order(1, kg=1000.0), _order(2, client_id=2, kg=1500.0, point=BALABANOVO)],
        trucks=[_truck(1, capacity=1200.0, reefer=False)],
        weather=SolverWeather(temperature_c=35.0, precipitation_mm=0.0, mode="heatwave_35c"),
    )

    outcome = run_solver(solver_input)
    metrics = outcome.metrics

    expected_tco = (
        metrics.total_trip_cost_rub
        + metrics.total_spoilage_loss_rub
        + metrics.total_unmet_penalty_rub
    )
    assert metrics.total_tco_rub == pytest.approx(expected_tco, abs=0.05)
    assert metrics.shipped_kg + metrics.unmet_kg == pytest.approx(2500.0, abs=0.02)
    assert 0.0 <= metrics.avg_freshness_pct <= 100.0
    assert "heat_without_reefer" in {warning.code for warning in outcome.warnings}


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


def test_empty_demand_returns_empty_plan() -> None:
    solver_input = _make_input(orders=[], trucks=[_truck(1)])

    outcome = run_solver(solver_input)

    assert outcome.routes == ()
    assert outcome.metrics.shipped_kg == 0.0
    assert outcome.metrics.unmet_kg == 0.0
    assert outcome.metrics.total_tco_rub == 0.0
    assert outcome.metrics.expected_net_profit_rub == 0.0


def test_tiny_time_limit_still_returns_a_valid_plan() -> None:
    solver_input = _make_input(
        orders=[_order(1, kg=900.0), _order(2, client_id=2, kg=900.0, point=BOROVSK)],
        trucks=[_truck(1, capacity=1200.0)],
    )

    outcome = run_solver(solver_input, time_limit_sec=0.01)

    assert outcome.allocation_method in {"milp", "greedy"}
    assert outcome.metrics.shipped_kg <= 1200.0 + 1e-6
    assert outcome.metrics.shipped_kg + outcome.metrics.unmet_kg == pytest.approx(1800.0, abs=0.05)


def test_solve_async_matches_sync_result() -> None:
    solver_input = _make_input(
        orders=[_order(1, kg=800.0)],
        trucks=[_truck(1)],
    )

    sync_outcome = run_solver(solver_input)
    async_outcome = asyncio.run(solve_async(solver_input))

    assert async_outcome.metrics == sync_outcome.metrics
    assert len(async_outcome.routes) == len(sync_outcome.routes)

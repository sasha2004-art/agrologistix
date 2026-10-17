"""Hard-constraint tests for the solver engine."""

import asyncio

import pytest
from app.schemas.enums import RoadType, TruckStatus, WarningSeverity
from app.services.solver_engine import SolverWeather, run_solver, solve_async
from tests.solver_factory import (
    BALABANOVO,
    BOROVSK,
    DETCHINO,
    KALUGA,
    _make_input,
    _order,
    _stock,
    _truck,
    _warehouse,
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


def test_dirt_unreachable_warning_targets_only_dirt_orders() -> None:
    solver_input = _make_input(
        orders=[
            _order(1, road_type=RoadType.ASPHALT, point=KALUGA),
            _order(2, client_id=2, road_type=RoadType.DIRT, point=BOROVSK),
        ],
        trucks=[_truck(1, dirt=False)],
    )

    outcome = run_solver(solver_input)
    dirt_warnings = [warning for warning in outcome.warnings if warning.code == "dirt_unreachable"]

    assert len(dirt_warnings) == 1
    assert dirt_warnings[0].order_id == 2
    assert outcome.metrics.shipped_kg == pytest.approx(1000.0, abs=0.01)


def test_all_trucks_broken_dirt_warnings_match_dirt_orders_only() -> None:
    solver_input = _make_input(
        orders=[
            _order(1, road_type=RoadType.ASPHALT, point=KALUGA),
            _order(2, client_id=2, road_type=RoadType.DIRT, point=BOROVSK),
        ],
        trucks=[_truck(1, status=TruckStatus.BROKEN)],
    )

    outcome = run_solver(solver_input)

    assert len([warning for warning in outcome.warnings if warning.code == "dirt_unreachable"]) == 1
    assert outcome.metrics.unmet_kg == pytest.approx(2000.0, abs=0.01)

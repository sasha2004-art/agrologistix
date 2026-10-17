"""Trip limits: stops per truck, shift length and freshness warnings (stage 2)."""

from dataclasses import replace

import pytest
from app.services import solver_allocation
from app.services.solver_engine import run_solver
from tests.solver_factory import BALABANOVO, BOROVSK, KALUGA, _make_input, _order, _stock, _truck

TOLERANCE = 1e-6


def _input_with_limits(**limits: object):
    orders = [
        _order(1, client_id=1, kg=300.0, point=KALUGA),
        _order(2, client_id=2, kg=300.0, point=BOROVSK),
        _order(3, client_id=3, kg=300.0, point=BALABANOVO),
        _order(4, client_id=4, kg=300.0, point=KALUGA),
        _order(5, client_id=5, kg=300.0, point=BOROVSK),
    ]
    solver_input = _make_input(
        orders=orders,
        trucks=[_truck(1, capacity=5000.0), _truck(2, capacity=5000.0)],
        stocks=[_stock(kg=5000.0)],
    )
    return replace(solver_input, **limits)


def test_stop_limit_trims_routes_and_reports_unmet() -> None:
    outcome = run_solver(_input_with_limits(max_stops_per_trip=2))

    codes = {warning.code for warning in outcome.warnings}
    assert all(len(route.stops) <= 2 for route in outcome.routes)
    assert outcome.metrics.total_trips <= 2
    assert outcome.metrics.shipped_kg == pytest.approx(1200.0, abs=TOLERANCE)
    assert outcome.metrics.unmet_kg == pytest.approx(300.0, abs=TOLERANCE)
    assert "trip_limit_exceeded" in codes


def test_stop_limit_is_enforced_when_milp_solution_is_rejected() -> None:
    class _NoSolution:
        x = None
        status = 2
        message = "time limit"

    original = solver_allocation.milp
    solver_allocation.milp = lambda **_kwargs: _NoSolution()  # type: ignore[assignment]
    try:
        outcome = run_solver(_input_with_limits(max_stops_per_trip=2))
    finally:
        solver_allocation.milp = original  # type: ignore[assignment]

    assert outcome.allocation_method == "greedy"
    assert all(len(route.stops) <= 2 for route in outcome.routes)
    assert outcome.metrics.shipped_kg <= 1200.0 + TOLERANCE
    assert "trip_limit_exceeded" in {warning.code for warning in outcome.warnings}


def test_shift_limit_cuts_late_stops_and_marks_them_unmet() -> None:
    outcome = run_solver(_input_with_limits(max_trip_hours=0.05))

    codes = {warning.code for warning in outcome.warnings}
    assert outcome.routes == ()
    assert outcome.metrics.shipped_kg == 0.0
    assert outcome.metrics.unmet_kg == pytest.approx(1500.0, abs=TOLERANCE)
    assert "trip_limit_exceeded" in codes


def test_freshness_floor_warns_without_dropping_cargo() -> None:
    """The TCO already prices spoilage, so the plan keeps the customer."""

    solver_input = _input_with_limits(min_stop_freshness=0.999)

    outcome = run_solver(solver_input)

    codes = {warning.code for warning in outcome.warnings}
    assert outcome.metrics.shipped_kg == pytest.approx(1500.0, abs=TOLERANCE)
    assert outcome.metrics.unmet_kg == pytest.approx(0.0, abs=TOLERANCE)
    assert "freshness_risk" in codes
    risky = [warning for warning in outcome.warnings if warning.code == "freshness_risk"]
    assert all(warning.order_id is not None for warning in risky)
    assert all(warning.client_id is not None for warning in risky)


def test_default_limits_keep_the_seed_plan_intact() -> None:
    solver_input = _input_with_limits()

    outcome = run_solver(solver_input)

    assert outcome.metrics.shipped_kg == pytest.approx(1500.0, abs=TOLERANCE)
    assert outcome.metrics.unmet_kg == pytest.approx(0.0, abs=TOLERANCE)
    assert "trip_limit_exceeded" not in {warning.code for warning in outcome.warnings}
    assert all(len(route.stops) <= 5 for route in outcome.routes)
    assert all(
        stop.eta_minutes <= solver_input.max_trip_hours * 60.0
        for route in outcome.routes
        for stop in route.stops
    )

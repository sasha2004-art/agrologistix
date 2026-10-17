"""Local search over the real route TCO (stage 3): merge, moves and budgets."""

from dataclasses import replace

import pytest
from app.services import solver_engine
from app.services.solver_allocation import AllocationResult, TruckLoad
from app.services.solver_contract import SolverInput
from app.services.solver_engine import run_solver
from app.services.solver_improve import improve_allocation
from app.services.solver_routing import LegIndex
from fastapi.testclient import TestClient
from tests.solver_factory import BOROVSK, KALUGA, _make_input, _order, _stock, _truck

AUTH = {"X-Access-Pin": "123456"}
OPTIMIZE_URL = "/api/v1/solver/optimize"


def _two_trip_draft(solver_input: SolverInput, orders, trucks) -> AllocationResult:
    """A wasteful draft: two trips although one truck could carry everything."""

    return AllocationResult(
        truck_loads=(
            TruckLoad(truck=trucks[0], loads=((orders[0], 500.0),)),
            TruckLoad(truck=trucks[1], loads=((orders[1], 500.0),)),
        ),
        unmet={},
        method="milp",
        unreachable_order_ids=frozenset(),
    )


def test_merge_releases_a_truck_and_lowers_the_real_tco() -> None:
    orders = [
        _order(1, client_id=1, kg=500.0, point=KALUGA, price=300.0),
        _order(2, client_id=2, kg=500.0, point=BOROVSK, price=300.0),
    ]
    trucks = [
        _truck(1, capacity=20000.0, cost_km=50.0, fixed=8000.0),
        _truck(2, capacity=6000.0, cost_km=50.0, fixed=8000.0),
    ]
    solver_input = _make_input(
        orders=orders,
        trucks=trucks,
        stocks=[_stock(kg=5000.0)],
    )
    draft = _two_trip_draft(solver_input, orders, trucks)

    improved = improve_allocation(
        solver_input,
        draft,
        orders,
        trucks,
        LegIndex(solver_input.legs),
    )

    assert len(improved.truck_loads) == 1
    assert improved.method == "milp+improved"
    improved_outcome = run_solver(
        replace(solver_input, improve_max_evaluations=0),
        time_limit_sec=1.0,
    )
    assert sum(load.truck.capacity_kg for load in improved.truck_loads) <= sum(
        load.truck.capacity_kg for load in draft.truck_loads
    )
    assert improved_outcome.metrics.shipped_kg > 0  # draft stays a valid solver input


def test_merge_is_skipped_when_capacity_forbids_it() -> None:
    orders = [
        _order(1, client_id=1, kg=500.0, point=KALUGA, price=300.0),
        _order(2, client_id=2, kg=500.0, point=BOROVSK, price=300.0),
    ]
    trucks = [
        _truck(1, capacity=600.0, cost_km=50.0, fixed=8000.0),
        _truck(2, capacity=600.0, cost_km=50.0, fixed=8000.0),
    ]
    solver_input = _make_input(orders=orders, trucks=trucks, stocks=[_stock(kg=5000.0)])
    draft = _two_trip_draft(solver_input, orders, trucks)

    improved = improve_allocation(
        solver_input,
        draft,
        orders,
        trucks,
        LegIndex(solver_input.legs),
    )

    assert improved.method == draft.method
    assert improved == draft


def test_improve_respects_the_evaluation_budget() -> None:
    orders = [
        _order(1, client_id=1, kg=500.0, point=KALUGA),
        _order(2, client_id=2, kg=500.0, point=BOROVSK),
    ]
    trucks = [_truck(1, capacity=6000.0), _truck(2, capacity=6000.0)]
    solver_input = replace(
        _make_input(orders=orders, trucks=trucks, stocks=[_stock(kg=5000.0)]),
        improve_max_evaluations=0,
    )
    draft = _two_trip_draft(solver_input, orders, trucks)

    improved = improve_allocation(
        solver_input,
        draft,
        orders,
        trucks,
        LegIndex(solver_input.legs),
    )

    assert improved is draft


def test_improve_is_deterministic() -> None:
    orders = [
        _order(1, client_id=1, kg=500.0, point=KALUGA, price=300.0),
        _order(2, client_id=2, kg=500.0, point=BOROVSK, price=300.0),
    ]
    trucks = [_truck(1, capacity=20000.0), _truck(2, capacity=6000.0)]
    solver_input = _make_input(orders=orders, trucks=trucks, stocks=[_stock(kg=5000.0)])
    draft = _two_trip_draft(solver_input, orders, trucks)

    first = run_solver(solver_input)
    second = run_solver(solver_input)

    assert first.metrics == second.metrics
    assert [
        (route.truck_id, [stop.order_id for stop in route.stops]) for route in first.routes
    ] == [(route.truck_id, [stop.order_id for stop in route.stops]) for route in second.routes]
    assert improve_allocation(
        solver_input, draft, orders, trucks, LegIndex(solver_input.legs)
    ) == improve_allocation(solver_input, draft, orders, trucks, LegIndex(solver_input.legs))


def _baseline(client: TestClient) -> dict:
    response = client.post(OPTIMIZE_URL, headers=AUTH, json={"mode": "baseline"})
    assert response.status_code == 200
    return response.json()


def test_seed_plan_is_never_worse_with_the_local_search(client: TestClient) -> None:
    with_search = _baseline(client)

    original = solver_engine.improve_allocation
    solver_engine.improve_allocation = lambda _input, allocation, *_args: allocation
    try:
        without_search = _baseline(client)
    finally:
        solver_engine.improve_allocation = original

    with_metrics = with_search["metrics"]
    plain_metrics = without_search["metrics"]
    assert with_metrics["total_tco_rub"] <= plain_metrics["total_tco_rub"] + 0.01
    assert with_metrics["split_clients"] <= plain_metrics["split_clients"]
    assert with_metrics["unmet_kg"] <= plain_metrics["unmet_kg"] + 0.001
    assert with_metrics["shipped_kg"] >= plain_metrics["shipped_kg"] - 0.001


def test_local_search_keeps_one_shop_per_truck_in_what_if(client: TestClient) -> None:
    baseline = _baseline(client)
    assert (
        client.patch(
            "/api/v1/erp/trucks/1",
            headers=AUTH,
            json={"status": "broken"},
        ).status_code
        == 200
    )

    what_if = client.post(
        OPTIMIZE_URL,
        headers=AUTH,
        json={"mode": "what_if", "baseline_run_id": baseline["run_id"]},
    ).json()

    assert what_if["metrics"]["split_clients"] == 0
    assert what_if["metrics"]["shipped_kg"] == baseline["metrics"]["shipped_kg"]


def test_solver_stays_within_the_time_budget(client: TestClient) -> None:
    import time

    started = time.perf_counter()
    _baseline(client)
    elapsed = time.perf_counter() - started

    assert elapsed < 1.5


@pytest.mark.parametrize("evaluations", [0, 25])
def test_budget_does_not_change_feasibility(evaluations: int) -> None:
    orders = [
        _order(1, client_id=1, kg=900.0, point=KALUGA),
        _order(2, client_id=2, kg=900.0, point=BOROVSK),
    ]
    trucks = [_truck(1, capacity=1000.0), _truck(2, capacity=1000.0)]
    solver_input = replace(
        _make_input(orders=orders, trucks=trucks, stocks=[_stock(kg=1000.0)]),
        improve_max_evaluations=evaluations,
    )

    outcome = run_solver(solver_input)

    assert outcome.metrics.shipped_kg <= 1000.0 + 1e-6
    for route in outcome.routes:
        capacity = next(t.capacity_kg for t in trucks if t.truck_id == route.truck_id)
        assert sum(stop.shipped_kg for stop in route.stops) <= capacity + 1e-6

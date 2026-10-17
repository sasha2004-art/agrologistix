"""Route consolidation: client grouping and trip telemetry (stage 0+1)."""

import json
from dataclasses import replace

import pytest
from app.models.erp_models import ClientOrder, Truck
from app.services import solver_allocation
from app.services.solver_engine import run_solver
from fastapi.testclient import TestClient
from sqlmodel import Session, select
from tests.solver_factory import _make_input, _order, _stock, _truck

AUTH = {"X-Access-Pin": "123456"}
OPTIMIZE_URL = "/api/v1/solver/optimize"

TOLERANCE = 1e-6


def _database_session(client: TestClient) -> Session:
    return Session(client.app.state.db_engine)  # type: ignore[attr-defined]


def _baseline(client: TestClient) -> dict:
    response = client.post(OPTIMIZE_URL, headers=AUTH, json={})
    assert response.status_code == 200
    return response.json()


def _client_trucks(payload: dict) -> dict[int, set[int]]:
    visited: dict[int, set[int]] = {}
    for route in payload["routes"]:
        for stop in route["stops"]:
            visited.setdefault(stop["client_id"], set()).add(route["truck_id"])
    return visited


def test_metrics_expose_trip_telemetry(client: TestClient) -> None:
    payload = _baseline(client)
    metrics = payload["metrics"]
    used_trucks = {route["truck_id"] for route in payload["routes"]}
    with _database_session(client) as session:
        capacity = sum(
            truck.capacity_kg
            for truck in session.exec(select(Truck)).all()
            if truck.id in used_trucks
        )

    assert metrics["total_trips"] == len(payload["routes"])
    assert 0.0 < metrics["avg_load_factor_pct"] <= 100.0
    assert metrics["avg_load_factor_pct"] == pytest.approx(
        metrics["shipped_kg"] / capacity * 100.0, abs=0.05
    )


def test_one_shop_is_served_by_one_truck_on_the_seed(client: TestClient) -> None:
    payload = _baseline(client)
    visited = _client_trucks(payload)

    assert payload["metrics"]["shipped_kg"] == 4175.0
    assert payload["metrics"]["unmet_kg"] == 0.0
    assert payload["metrics"]["split_clients"] == 0
    assert all(len(truck_ids) == 1 for truck_ids in visited.values())


def test_consolidation_uses_two_trips_instead_of_three(client: TestClient) -> None:
    """Ground orders force one offroad truck, so two trips is the lower bound."""

    payload = _baseline(client)

    assert payload["metrics"]["total_trips"] == 2
    assert len(payload["routes"]) == 2
    # Объёмы магазинов не набивают машины под завязку: важна сама консолидация.
    assert payload["metrics"]["avg_load_factor_pct"] > 30.0


def test_client_orders_with_same_coordinates_share_a_truck(client: TestClient) -> None:
    payload = _baseline(client)

    with _database_session(client) as session:
        orders = session.exec(select(ClientOrder)).all()

    trucks_by_order: dict[int, set[int]] = {}
    for route in payload["routes"]:
        for stop in route["stops"]:
            if stop["order_id"] is not None:
                trucks_by_order.setdefault(stop["order_id"], set()).add(route["truck_id"])

    for client in {order.client_id for order in orders}:
        client_orders = [order.id for order in orders if order.client_id == client]
        client_trucks = {
            truck_id
            for order_id in client_orders
            for truck_id in trucks_by_order.get(order_id, set())
        }
        assert len(client_trucks) == 1


def test_split_mode_is_used_only_when_it_moves_more_cargo() -> None:
    """One client, two orders, two small trucks: strict grouping would leave cargo."""

    orders = [
        _order(1, client_id=1, kg=1000.0, penalty=200.0),
        _order(2, client_id=1, kg=1000.0, penalty=200.0),
    ]
    solver_input = replace(
        _make_input(
            orders=orders,
            trucks=[_truck(1, capacity=1200.0), _truck(2, capacity=1200.0)],
            stocks=[_stock(kg=5000.0)],
        ),
        client_split_penalty_rub=1000.0,
    )

    outcome = run_solver(solver_input)

    assert outcome.metrics.unmet_kg == pytest.approx(0.0, abs=TOLERANCE)
    assert outcome.metrics.shipped_kg == pytest.approx(2000.0, abs=TOLERANCE)
    assert outcome.metrics.total_trips == 2
    assert outcome.metrics.split_clients == 1


def test_capacity_alone_never_splits_a_client_that_fits() -> None:
    orders = [
        _order(1, client_id=1, kg=400.0, penalty=200.0),
        _order(2, client_id=1, kg=400.0, penalty=200.0),
    ]
    solver_input = _make_input(
        orders=orders,
        trucks=[_truck(1, capacity=1200.0), _truck(2, capacity=1200.0)],
        stocks=[_stock(kg=5000.0)],
    )

    outcome = run_solver(solver_input)

    assert outcome.metrics.split_clients == 0
    assert outcome.metrics.total_trips == 1
    assert outcome.metrics.shipped_kg == pytest.approx(800.0, abs=TOLERANCE)


def test_greedy_fallback_keeps_client_orders_together(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class _NoSolution:
        x = None
        status = 2
        message = "time limit"

    monkeypatch.setattr(solver_allocation, "milp", lambda **_kwargs: _NoSolution())
    orders = [
        _order(1, client_id=1, kg=300.0, penalty=100.0),
        _order(2, client_id=1, kg=300.0, penalty=100.0),
        _order(3, client_id=2, kg=300.0, penalty=50.0),
    ]
    solver_input = _make_input(
        orders=orders,
        trucks=[_truck(1, capacity=1000.0), _truck(2, capacity=1000.0)],
        stocks=[_stock(kg=5000.0)],
    )

    outcome = run_solver(solver_input)

    assert outcome.allocation_method.startswith("greedy")
    assert outcome.metrics.split_clients == 0
    assert outcome.metrics.shipped_kg == pytest.approx(900.0, abs=TOLERANCE)


@pytest.mark.parametrize("mode", ["normal", "heatwave_35c", "heavy_rain"])
def test_trip_metrics_stay_consistent_for_every_preset(client: TestClient, mode: str) -> None:
    client.post("/api/v1/weather/override", headers=AUTH, json={"mode": mode})

    payload = _baseline(client)
    metrics = payload["metrics"]
    visited = _client_trucks(payload)

    assert metrics["total_trips"] == len(payload["routes"])
    assert metrics["split_clients"] == sum(
        1 for truck_ids in visited.values() if len(truck_ids) > 1
    )
    assert json.dumps(payload)  # response stays JSON-serializable

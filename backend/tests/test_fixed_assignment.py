"""Зафиксированный маршрут заявки «В работе»: хранение, списание и расчёт."""

import pytest
from app.models.erp_models import ClientOrder, WarehouseStock
from fastapi.testclient import TestClient
from sqlmodel import Session, select

AUTH = {"X-Access-Pin": "123456"}
ADMIN = {"X-Access-Pin": "654321"}
ASSIGN_URL = "/api/v1/erp/orders/{order_id}/assign"
PATCH_URL = "/api/v1/erp/orders/{order_id}"
OPTIMIZE_URL = "/api/v1/solver/optimize"
STATE_URL = "/api/v1/erp/state"


def _database_session(client: TestClient) -> Session:
    return Session(client.app.state.db_engine)  # type: ignore[attr-defined]


def _assign(client: TestClient, order_id: int = 1) -> dict:
    response = client.post(ASSIGN_URL.format(order_id=order_id), headers=AUTH)
    assert response.status_code == 200
    return response.json()


def _state(client: TestClient) -> dict:
    response = client.get(STATE_URL, headers=AUTH)
    assert response.status_code == 200
    return response.json()


def _set_status(client: TestClient, order_id: int, status: str) -> None:
    response = client.patch(
        PATCH_URL.format(order_id=order_id), headers=AUTH, json={"delivery_status": status}
    )
    assert response.status_code == 200


def _stock_kg(client: TestClient, warehouse_id: int, product_id: int) -> float:
    with _database_session(client) as session:
        stock = session.exec(
            select(WarehouseStock).where(
                WarehouseStock.warehouse_id == warehouse_id,
                WarehouseStock.product_id == product_id,
            )
        ).one()
    return stock.available_kg


def test_assign_stores_the_fixed_route_with_geometry(client: TestClient) -> None:
    assignment = _assign(client)
    assert assignment["geometry"]

    fixed = [item for item in _state(client)["fixed_assignments"] if item["order_id"] == 1]

    assert len(fixed) == 1
    assert fixed[0]["truck_id"] == assignment["truck_id"]
    assert fixed[0]["warehouse_id"] == assignment["warehouse_id"]
    assert fixed[0]["shipped_kg"] == pytest.approx(assignment["shipped_kg"], abs=0.01)
    assert len(fixed[0]["geometry"]) == len(assignment["geometry"])


def test_reassigning_an_order_updates_the_same_fixed_route(client: TestClient) -> None:
    first = _assign(client)
    second = _assign(client)

    fixed = [item for item in _state(client)["fixed_assignments"] if item["order_id"] == 1]

    assert len(fixed) == 1
    assert fixed[0]["truck_id"] == second["truck_id"]
    assert first["order_id"] == second["order_id"] == 1


def test_in_progress_writes_off_the_fixed_warehouse(client: TestClient) -> None:
    assignment = _assign(client)
    before = _stock_kg(client, assignment["warehouse_id"], 1)

    _set_status(client, 1, "in_progress")

    after = _stock_kg(client, assignment["warehouse_id"], 1)
    assert after == pytest.approx(before - assignment["shipped_kg"], abs=0.01)


def test_pending_returns_the_route_and_restores_the_stock(client: TestClient) -> None:
    assignment = _assign(client)
    before = _stock_kg(client, assignment["warehouse_id"], 1)
    _set_status(client, 1, "in_progress")

    _set_status(client, 1, "pending")

    assert _state(client)["fixed_assignments"] == []
    assert _stock_kg(client, assignment["warehouse_id"], 1) == pytest.approx(before, abs=0.01)


def test_delivered_drops_the_fixed_route(client: TestClient) -> None:
    _assign(client)

    _set_status(client, 1, "delivered")

    assert _state(client)["fixed_assignments"] == []


def test_plan_includes_the_fixed_route_and_keeps_the_truck_busy(client: TestClient) -> None:
    assignment = _assign(client)
    with _database_session(client) as session:
        order = session.get(ClientOrder, 1)
    assert order is not None
    ordered_kg = order.requested_kg

    _set_status(client, 1, "in_progress")
    plan = client.post(OPTIMIZE_URL, headers=AUTH, json={}).json()

    fixed_routes = [
        route for route in plan["routes"] if route["truck_id"] == assignment["truck_id"]
    ]
    assert len(fixed_routes) == 1
    stops = fixed_routes[0]["stops"]
    assert len(stops) == 1
    assert stops[0]["order_id"] == 1
    assert stops[0]["shipped_kg"] == pytest.approx(ordered_kg, abs=0.01)
    assert fixed_routes[0]["geometry"]

    # Зафиксированная машина больше не везёт другие заявки, а её груз учтён.
    other_stops = [
        stop
        for route in plan["routes"]
        if route["truck_id"] != assignment["truck_id"]
        for stop in route["stops"]
    ]
    assert all(stop["order_id"] != 1 for stop in other_stops)
    assert plan["metrics"]["shipped_kg"] >= ordered_kg - 0.01


def test_reset_demo_clears_fixed_routes(client: TestClient) -> None:
    _assign(client)
    assert _state(client)["fixed_assignments"]

    assert client.post("/api/v1/system/reset-demo", headers=ADMIN).status_code == 200

    assert _state(client)["fixed_assignments"] == []

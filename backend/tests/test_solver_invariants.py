"""End-to-end invariants of a plan, checked across weather and fleet states."""

import pytest
from app.models.erp_models import Truck
from fastapi.testclient import TestClient
from sqlmodel import Session, select

AUTH = {"X-Access-Pin": "123456"}
OPTIMIZE_URL = "/api/v1/solver/optimize"
STATE_URL = "/api/v1/erp/state"
WEATHER_URL = "/api/v1/weather/override"
TRUCKS_URL = "/api/v1/erp/trucks"

TOLERANCE = 1e-6


def _database_session(client: TestClient) -> Session:
    return Session(client.app.state.db_engine)  # type: ignore[attr-defined]


def _state(client: TestClient) -> dict:
    response = client.get(STATE_URL, headers=AUTH)
    assert response.status_code == 200
    return response.json()


def _pending_demand_kg(state: dict) -> float:
    return sum(
        order["requested_kg"] - order["delivered_kg"]
        for order in state["orders"]
        if order["delivery_status"] == "pending"
    )


def _break_reefers(client: TestClient) -> None:
    with _database_session(client) as session:
        for truck in session.exec(select(Truck)).all():
            if truck.has_reefer:
                truck.status = "broken"
                session.add(truck)
        session.commit()


def _break_everything(client: TestClient) -> None:
    with _database_session(client) as session:
        for truck in session.exec(select(Truck)).all():
            truck.status = "broken"
            session.add(truck)
        session.commit()


def _assert_plan_invariants(state: dict, payload: dict) -> None:
    metrics = payload["metrics"]
    trucks = {truck["id"]: truck for truck in state["trucks"]}
    clients = {client["id"]: client for client in state["clients"]}
    stock_left = {
        (stock["warehouse_id"], stock["product_id"]): stock["available_kg"]
        for stock in state["stocks"]
    }
    shipped_by_stock: dict[tuple[int, int], float] = {}

    assert metrics["shipped_kg"] + metrics["unmet_kg"] == pytest.approx(
        _pending_demand_kg(state), abs=TOLERANCE
    )
    assert metrics["total_tco_rub"] == pytest.approx(
        metrics["total_trip_cost_rub"]
        + metrics["total_spoilage_loss_rub"]
        + metrics["total_unmet_penalty_rub"],
        abs=0.05,
    )
    assert 0.0 <= metrics["avg_freshness_pct"] <= 100.0

    for route in payload["routes"]:
        truck = trucks[route["truck_id"]]
        stops = route["stops"]
        assert truck["status"] == "active"
        assert stops
        assert sum(stop["shipped_kg"] for stop in stops) <= truck["capacity_kg"] + TOLERANCE
        assert [stop["sequence_order"] for stop in stops] == list(range(1, len(stops) + 1))
        assert [stop["eta_minutes"] for stop in stops] == sorted(
            stop["eta_minutes"] for stop in stops
        )
        for stop in stops:
            assert stop["order_id"] is not None
            assert stop["shipped_kg"] > 0.0
            assert 0.0 < stop["expected_freshness"] <= 1.0
            assert stop["trip_leg_cost_rub"] >= 0.0
            if clients[stop["client_id"]]["road_type"] == "dirt":
                assert truck["can_use_dirt"] is True
            key = (stop["warehouse_id"], stop["product_id"])
            shipped_by_stock[key] = shipped_by_stock.get(key, 0.0) + stop["shipped_kg"]

    for key, shipped_kg in shipped_by_stock.items():
        assert shipped_kg <= stock_left.get(key, 0.0) + TOLERANCE

    if metrics["unmet_kg"] > 0:
        assert "unmet_demand" in {warning["code"] for warning in payload["warnings"]}
    if payload["routes"]:
        assert metrics["total_trip_cost_rub"] > 0.0 and metrics["shipped_kg"] > 0.0


@pytest.mark.parametrize("mode", ["normal", "heatwave_35c", "heavy_rain"])
def test_plan_invariants_hold_for_every_weather_preset(client: TestClient, mode: str) -> None:
    assert client.post(WEATHER_URL, headers=AUTH, json={"mode": mode}).status_code == 200

    payload = client.post(OPTIMIZE_URL, headers=AUTH, json={"mode": "baseline"}).json()

    assert payload["metrics"]["shipped_kg"] > 0.0
    _assert_plan_invariants(_state(client), payload)


def test_invariants_hold_without_reefers_in_the_heat(client: TestClient) -> None:
    client.post(WEATHER_URL, headers=AUTH, json={"mode": "heatwave_35c"})
    _break_reefers(client)

    payload = client.post(OPTIMIZE_URL, headers=AUTH, json={"mode": "baseline"}).json()

    _assert_plan_invariants(_state(client), payload)
    assert "heat_without_reefer" in {warning["code"] for warning in payload["warnings"]}


def test_invariants_hold_with_a_partially_broken_fleet(client: TestClient) -> None:
    assert (
        client.patch(f"{TRUCKS_URL}/1", headers=AUTH, json={"status": "broken"}).status_code == 200
    )

    payload = client.post(OPTIMIZE_URL, headers=AUTH, json={"mode": "baseline"}).json()

    _assert_plan_invariants(_state(client), payload)
    assert 1 not in {route["truck_id"] for route in payload["routes"]}
    assert "broken_trucks_excluded" in {warning["code"] for warning in payload["warnings"]}


def test_everything_unmet_without_trucks(client: TestClient) -> None:
    _break_everything(client)

    payload = client.post(OPTIMIZE_URL, headers=AUTH, json={"mode": "baseline"}).json()
    state = _state(client)

    assert payload["routes"] == []
    assert payload["metrics"]["shipped_kg"] == 0.0
    assert payload["metrics"]["unmet_kg"] == pytest.approx(_pending_demand_kg(state), abs=TOLERANCE)
    assert {"no_active_trucks", "unmet_demand"} <= {
        warning["code"] for warning in payload["warnings"]
    }
    _assert_plan_invariants(state, payload)


def test_repeated_calculation_is_deterministic(client: TestClient) -> None:
    first = client.post(OPTIMIZE_URL, headers=AUTH, json={"mode": "baseline"}).json()
    second = client.post(OPTIMIZE_URL, headers=AUTH, json={"mode": "baseline"}).json()

    assert second["run_id"] > first["run_id"]
    assert second["metrics"] == first["metrics"]
    assert [
        (route["truck_id"], [(stop["order_id"], stop["shipped_kg"]) for stop in route["stops"]])
        for route in second["routes"]
    ] == [
        (route["truck_id"], [(stop["order_id"], stop["shipped_kg"]) for stop in route["stops"]])
        for route in first["routes"]
    ]

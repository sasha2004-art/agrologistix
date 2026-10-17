"""What-if scenario tests: recalculation, frozen orders and comparison delta."""

import pytest
from app.models.erp_models import ClientOrder, Truck
from app.models.run_models import RouteStop, SimulationRun
from fastapi.testclient import TestClient
from sqlmodel import Session, select

AUTH = {"X-Access-Pin": "123456"}
OPTIMIZE_URL = "/api/v1/solver/optimize"
ORDERS_URL = "/api/v1/erp/orders"
TRUCKS_URL = "/api/v1/erp/trucks"


def _database_session(client: TestClient) -> Session:
    return Session(client.app.state.db_engine)  # type: ignore[attr-defined]


@pytest.fixture
def baseline(client: TestClient) -> dict:
    return client.post(OPTIMIZE_URL, headers=AUTH, json={"mode": "baseline"}).json()


def _what_if(client: TestClient, baseline_run_id: int) -> dict:
    response = client.post(
        OPTIMIZE_URL,
        headers=AUTH,
        json={"mode": "what_if", "baseline_run_id": baseline_run_id},
    )
    assert response.status_code == 200
    return response.json()


def _shipped_order_ids(payload: dict) -> set[int]:
    return {stop["order_id"] for route in payload["routes"] for stop in route["stops"]}


def test_what_if_without_changes_reports_zero_delta(
    client: TestClient,
    baseline: dict,
) -> None:
    payload = _what_if(client, baseline["run_id"])

    assert payload["parent_run_id"] == baseline["run_id"]
    comparison = payload["comparison"]
    assert comparison is not None
    assert comparison["total_tco_rub"]["delta"] == 0.0
    assert comparison["shipped_kg"]["before"] == baseline["metrics"]["shipped_kg"]
    assert comparison["shipped_kg"]["after"] == payload["metrics"]["shipped_kg"]


def test_new_run_keeps_baseline_untouched(client: TestClient, baseline: dict) -> None:
    payload = _what_if(client, baseline["run_id"])

    with _database_session(client) as session:
        baseline_run = session.get(SimulationRun, baseline["run_id"])
        new_run = session.get(SimulationRun, payload["run_id"])
        baseline_stops = session.exec(
            select(RouteStop).where(RouteStop.run_id == baseline["run_id"])
        ).all()

    assert baseline_run is not None
    assert baseline_run.parent_run_id is None
    assert baseline_run.total_tco_rub == baseline["metrics"]["total_tco_rub"]
    assert len(baseline_stops) == sum(len(route["stops"]) for route in baseline["routes"])
    assert new_run is not None
    assert new_run.parent_run_id == baseline["run_id"]


def test_delivered_order_is_not_reassigned_but_its_client_keeps_other_orders(
    client: TestClient,
    baseline: dict,
) -> None:
    """One client has two orders; delivering one must not cancel the other."""

    with _database_session(client) as session:
        orders = session.exec(
            select(ClientOrder).where(ClientOrder.client_id == 1).order_by(ClientOrder.id)
        ).all()
    assert len(orders) >= 2
    delivered_id = int(orders[0].id or 0)
    remaining_id = int(orders[1].id or 0)

    assert (
        client.patch(
            f"{ORDERS_URL}/{delivered_id}",
            headers=AUTH,
            json={"delivery_status": "delivered"},
        ).status_code
        == 200
    )

    payload = _what_if(client, baseline["run_id"])
    shipped = _shipped_order_ids(payload)

    assert delivered_id not in shipped
    assert remaining_id in shipped
    assert payload["comparison"]["shipped_kg"]["before"] > payload["metrics"]["shipped_kg"]


def test_broken_truck_moves_its_load_to_unmet_or_other_trucks(
    client: TestClient,
    baseline: dict,
) -> None:
    with _database_session(client) as session:
        truck_ids = {
            stop.truck_id
            for stop in session.exec(
                select(RouteStop).where(RouteStop.run_id == baseline["run_id"])
            ).all()
        }
    assert truck_ids
    broken_truck_id = sorted(truck_ids)[0]

    assert (
        client.patch(
            f"{TRUCKS_URL}/{broken_truck_id}",
            headers=AUTH,
            json={"status": "broken"},
        ).status_code
        == 200
    )

    payload = _what_if(client, baseline["run_id"])

    assert broken_truck_id not in {route["truck_id"] for route in payload["routes"]}
    comparison = payload["comparison"]
    assert comparison["shipped_kg"]["delta"] <= 0
    assert "broken_trucks_excluded" in {warning["code"] for warning in payload["warnings"]}


def test_all_trucks_broken_sets_unmet_and_positive_penalty_delta(
    client: TestClient,
    baseline: dict,
) -> None:
    with _database_session(client) as session:
        for truck in session.exec(select(Truck)).all():
            truck.status = "broken"
            session.add(truck)
        session.commit()

    payload = _what_if(client, baseline["run_id"])
    comparison = payload["comparison"]

    assert payload["routes"] == []
    assert payload["metrics"]["unmet_kg"] > 0
    assert comparison["unmet_kg"]["before"] == 0.0
    assert comparison["unmet_kg"]["after"] > 0
    assert comparison["unmet_kg"]["delta_pct"] is None


def test_price_change_moves_the_delta(client: TestClient, baseline: dict) -> None:
    planned_order_id = next(
        stop["order_id"] for route in baseline["routes"] for stop in route["stops"]
    )

    with _database_session(client) as session:
        order = session.get(ClientOrder, planned_order_id)
    assert order is not None
    new_price = order.purchase_price_rub * 1.5

    client.patch(
        f"{ORDERS_URL}/{planned_order_id}",
        headers=AUTH,
        json={"purchase_price_rub": new_price},
    )

    payload = _what_if(client, baseline["run_id"])
    comparison = payload["comparison"]

    assert (
        comparison["total_spoilage_loss_rub"]["after"]
        > comparison["total_spoilage_loss_rub"]["before"]
    )
    assert comparison["total_tco_rub"]["delta"] > 0


def test_heatwave_moves_load_to_reefers_and_cuts_spoilage(
    client: TestClient,
    baseline: dict,
) -> None:
    """The solver prefers reefers in the heat even if trips become pricier."""

    client.post(
        "/api/v1/weather/override",
        headers=AUTH,
        json={"mode": "heatwave_35c"},
    )

    payload = _what_if(client, baseline["run_id"])
    comparison = payload["comparison"]

    with _database_session(client) as session:
        reefers = {truck.id: truck.has_reefer for truck in session.exec(select(Truck)).all()}

    assert comparison["total_spoilage_loss_rub"]["delta"] < 0
    assert comparison["avg_freshness_pct"]["delta"] > 0
    assert comparison["total_trip_cost_rub"]["delta"] > 0
    assert all(reefers[route["truck_id"]] is True for route in payload["routes"])


def test_heatwave_with_broken_reefers_spoils_cargo(
    client: TestClient,
    baseline: dict,
) -> None:
    """PRD scenario: +35 C and every reefer truck broken."""

    with _database_session(client) as session:
        for truck in session.exec(select(Truck)).all():
            if truck.has_reefer:
                truck.status = "broken"
                session.add(truck)
        session.commit()

    client.post(
        "/api/v1/weather/override",
        headers=AUTH,
        json={"mode": "heatwave_35c"},
    )

    payload = _what_if(client, baseline["run_id"])
    comparison = payload["comparison"]
    codes = {warning["code"] for warning in payload["warnings"]}

    assert comparison["avg_freshness_pct"]["delta"] < 0
    assert comparison["total_spoilage_loss_rub"]["delta"] > 0
    assert comparison["unmet_kg"]["after"] > 0
    assert {
        "broken_trucks_excluded",
        "unmet_demand",
        "heat_without_reefer",
    } <= codes


def test_full_prd_scenario_delivered_broken_price(client: TestClient, baseline: dict) -> None:
    """PATCH delivered order -> PATCH broken truck -> PATCH price -> what_if."""

    planned_order_ids = [
        stop["order_id"] for route in baseline["routes"] for stop in route["stops"]
    ]
    delivered_order_id = planned_order_ids[0]
    repriced_order_id = planned_order_ids[1]

    with _database_session(client) as session:
        truck = session.exec(select(Truck).order_by(Truck.id)).first()
        broken_truck_id = int(truck.id or 0) if truck else 0

    assert delivered_order_id and repriced_order_id and broken_truck_id

    assert (
        client.patch(
            f"{ORDERS_URL}/{delivered_order_id}",
            headers=AUTH,
            json={"delivery_status": "delivered"},
        ).status_code
        == 200
    )
    assert (
        client.patch(
            f"{TRUCKS_URL}/{broken_truck_id}",
            headers=AUTH,
            json={"status": "broken"},
        ).status_code
        == 200
    )
    assert (
        client.patch(
            f"{ORDERS_URL}/{repriced_order_id}",
            headers=AUTH,
            json={"purchase_price_rub": 500.0},
        ).status_code
        == 200
    )

    payload = _what_if(client, baseline["run_id"])

    assert delivered_order_id not in _shipped_order_ids(payload)
    assert broken_truck_id not in {route["truck_id"] for route in payload["routes"]}
    comparison = payload["comparison"]
    assert comparison["total_tco_rub"]["before"] == baseline["metrics"]["total_tco_rub"]
    assert comparison["total_tco_rub"]["after"] == payload["metrics"]["total_tco_rub"]
    assert comparison["total_tco_rub"]["delta"] == pytest.approx(
        payload["metrics"]["total_tco_rub"] - baseline["metrics"]["total_tco_rub"],
        abs=0.02,
    )
    codes = {warning["code"] for warning in payload["warnings"]}
    assert "broken_trucks_excluded" in codes

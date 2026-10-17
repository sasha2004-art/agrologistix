"""Подбор оптимальной машины и маршрута для заявки: /erp/orders/{id}/assign."""

import pytest
from app.models.erp_models import ClientOrder, Truck, WarehouseStock
from app.schemas.enums import TruckStatus
from fastapi.testclient import TestClient
from sqlmodel import Session, select

AUTH = {"X-Access-Pin": "123456"}
ADMIN = {"X-Access-Pin": "654321"}
ASSIGN_URL = "/api/v1/erp/orders/{order_id}/assign"


def _database_session(client: TestClient) -> Session:
    return Session(client.app.state.db_engine)  # type: ignore[attr-defined]


def _reset(client: TestClient) -> None:
    assert client.post("/api/v1/system/reset-demo", headers=ADMIN).status_code == 200


def test_assignment_reports_the_picked_truck_and_route(client: TestClient) -> None:
    with _database_session(client) as session:
        order = session.get(ClientOrder, 1)
    assert order is not None
    expected_kg = order.requested_kg - order.delivered_kg

    response = client.post(ASSIGN_URL.format(order_id=1), headers=AUTH)

    assert response.status_code == 200
    payload = response.json()
    assert payload["order_id"] == 1
    assert payload["truck_id"] > 0
    assert payload["warehouse_id"] > 0
    # Объём в ответе — остаток спроса заявки, а не хардкод из seed-набора.
    assert payload["shipped_kg"] == pytest.approx(expected_kg, abs=0.01)
    assert payload["distance_km"] > 0.0
    assert payload["duration_min"] > 0.0
    assert 0.5 <= payload["expected_freshness"] <= 1.0
    assert payload["total_cost_rub"] == pytest.approx(
        payload["trip_cost_rub"] + payload["spoilage_loss_rub"], abs=0.05
    )


def test_assignment_respects_the_dirt_road_permission(client: TestClient) -> None:
    # Заявка 5 — кооператив Боровск с грунтовым подъездом.
    response = client.post(ASSIGN_URL.format(order_id=5), headers=AUTH)

    assert response.status_code == 200
    with _database_session(client) as session:
        truck = session.get(Truck, response.json()["truck_id"])
    assert truck is not None
    assert truck.can_use_dirt is True


def test_assignment_is_the_cheapest_fitting_option(client: TestClient) -> None:
    """Оставляем по одной машине: выбранный вариант дешевле любого другого."""

    baseline = client.post(ASSIGN_URL.format(order_id=1), headers=AUTH).json()

    totals: dict[int, float] = {}
    for truck_id in (1, 2, 3):
        _reset(client)
        with _database_session(client) as session:
            for truck in session.exec(select(Truck)).all():
                truck.status = (
                    TruckStatus.ACTIVE.value if truck.id == truck_id else TruckStatus.BROKEN.value
                )
                session.add(truck)
            session.commit()
        response = client.post(ASSIGN_URL.format(order_id=1), headers=AUTH)
        assert response.status_code == 200
        totals[truck_id] = response.json()["total_cost_rub"]
    _reset(client)

    assert baseline["truck_id"] in totals
    assert baseline["total_cost_rub"] == pytest.approx(min(totals.values()), abs=0.05)


def test_assignment_rejects_missing_stock(client: TestClient) -> None:
    with _database_session(client) as session:
        for stock in session.exec(
            select(WarehouseStock).where(WarehouseStock.product_id == 1)
        ).all():
            stock.available_kg = 0.0
            session.add(stock)
        session.commit()

    response = client.post(ASSIGN_URL.format(order_id=1), headers=AUTH)

    assert response.status_code == 409
    assert response.json()["code"] == "conflict"


def test_assignment_rejects_a_fleet_out_of_service(client: TestClient) -> None:
    with _database_session(client) as session:
        for truck in session.exec(select(Truck)).all():
            truck.status = TruckStatus.BROKEN.value
            session.add(truck)
        session.commit()

    response = client.post(ASSIGN_URL.format(order_id=1), headers=AUTH)

    assert response.status_code == 409


def test_assignment_does_not_change_the_persisted_state(client: TestClient) -> None:
    with _database_session(client) as session:
        before = {
            stock.id: stock.available_kg for stock in session.exec(select(WarehouseStock)).all()
        }

    assert client.post(ASSIGN_URL.format(order_id=1), headers=AUTH).status_code == 200

    with _database_session(client) as session:
        order = session.get(ClientOrder, 1)
        after = {
            stock.id: stock.available_kg for stock in session.exec(select(WarehouseStock)).all()
        }

    assert order is not None
    assert order.delivered_kg == 0.0
    assert order.delivery_status == "pending"
    assert after == before


def test_assignment_requires_pin_and_existing_order(client: TestClient) -> None:
    unauthorized = client.post(ASSIGN_URL.format(order_id=1))
    missing = client.post(ASSIGN_URL.format(order_id=9999), headers=AUTH)

    assert unauthorized.status_code == 401
    assert missing.status_code == 404

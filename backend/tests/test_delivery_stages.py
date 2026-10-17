"""Три этапа поставки: «В плане» → «В работе» → «Доставлено».

Отдельный файл, потому что ``test_delivery_stock.py`` уже упирается в лимит
500 строк на файл.
"""

import pytest
from app.models.erp_models import ClientOrder, WarehouseStock
from app.models.run_models import DeliveredOrderStock
from fastapi.testclient import TestClient
from sqlmodel import Session, select

AUTH = {"X-Access-Pin": "123456"}
OPTIMIZE_URL = "/api/v1/solver/optimize"
ORDERS_URL = "/api/v1/erp/orders"


def _database_session(client: TestClient) -> Session:
    return Session(client.app.state.db_engine)  # type: ignore[attr-defined]


def _stock_total(client: TestClient, product_id: int) -> float:
    with _database_session(client) as session:
        return sum(
            stock.available_kg
            for stock in session.exec(
                select(WarehouseStock).where(WarehouseStock.product_id == product_id)
            ).all()
        )


def test_in_progress_ships_stock_and_keeps_order_out_of_the_next_plan(
    client: TestClient,
) -> None:
    baseline = client.post(OPTIMIZE_URL, headers=AUTH, json={}).json()
    order_id = baseline["routes"][0]["stops"][0]["order_id"]

    with _database_session(client) as session:
        order = session.get(ClientOrder, order_id)
        assert order is not None
        product_id = order.product_id
        requested_kg = order.requested_kg
    stock_before = _stock_total(client, product_id)

    response = client.patch(
        f"{ORDERS_URL}/{order_id}",
        headers=AUTH,
        json={"delivery_status": "in_progress"},
    )

    assert response.status_code == 200
    assert response.json()["delivery_status"] == "in_progress"
    assert response.json()["delivered_kg"] == pytest.approx(requested_kg)

    with _database_session(client) as session:
        journal = session.exec(
            select(DeliveredOrderStock).where(DeliveredOrderStock.order_id == order_id)
        ).all()
    assert journal, "отгрузка «в работе» должна попадать в журнал списаний"
    assert stock_before - _stock_total(client, product_id) == pytest.approx(
        sum(entry.shipped_kg for entry in journal)
    )

    # Отгруженная заявка не перераспределяется: остаток спроса уже вывезен.
    replanned = client.post(OPTIMIZE_URL, headers=AUTH, json={}).json()
    shipped_ids = {stop["order_id"] for route in replanned["routes"] for stop in route["stops"]}
    assert order_id not in shipped_ids


def test_in_progress_to_delivered_does_not_write_off_stock_twice(client: TestClient) -> None:
    baseline = client.post(OPTIMIZE_URL, headers=AUTH, json={}).json()
    order_id = baseline["routes"][0]["stops"][0]["order_id"]

    with _database_session(client) as session:
        order = session.get(ClientOrder, order_id)
        assert order is not None
        product_id = order.product_id

    assert (
        client.patch(
            f"{ORDERS_URL}/{order_id}",
            headers=AUTH,
            json={"delivery_status": "in_progress"},
        ).status_code
        == 200
    )
    stock_after_shipment = _stock_total(client, product_id)

    response = client.patch(
        f"{ORDERS_URL}/{order_id}",
        headers=AUTH,
        json={"delivery_status": "delivered"},
    )

    assert response.status_code == 200
    assert response.json()["delivery_status"] == "delivered"
    assert _stock_total(client, product_id) == pytest.approx(stock_after_shipment)


def test_in_progress_can_be_rolled_back_to_pending(client: TestClient) -> None:
    baseline = client.post(OPTIMIZE_URL, headers=AUTH, json={}).json()
    order_id = baseline["routes"][0]["stops"][0]["order_id"]

    with _database_session(client) as session:
        order = session.get(ClientOrder, order_id)
        assert order is not None
        product_id = order.product_id
    stock_before = _stock_total(client, product_id)

    assert (
        client.patch(
            f"{ORDERS_URL}/{order_id}",
            headers=AUTH,
            json={"delivery_status": "in_progress"},
        ).status_code
        == 200
    )

    response = client.patch(
        f"{ORDERS_URL}/{order_id}",
        headers=AUTH,
        json={"delivery_status": "pending"},
    )

    assert response.status_code == 200
    assert response.json()["delivery_status"] == "pending"
    assert response.json()["delivered_kg"] == pytest.approx(0.0)
    assert _stock_total(client, product_id) == pytest.approx(stock_before)

    with _database_session(client) as session:
        assert (
            session.exec(
                select(DeliveredOrderStock).where(DeliveredOrderStock.order_id == order_id)
            ).all()
            == []
        )

    # Возвращённая заявка снова участвует в расчёте.
    replanned = client.post(OPTIMIZE_URL, headers=AUTH, json={}).json()
    shipped_ids = {stop["order_id"] for route in replanned["routes"] for stop in route["stops"]}
    assert order_id in shipped_ids

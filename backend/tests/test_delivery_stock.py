"""Delivery accounting: stock write-off, partial deliveries and what-if demand."""

import pytest
from app.models.erp_models import ClientOrder, Truck, WarehouseStock
from app.models.run_models import DeliveredOrderStock, RouteStop, SimulationRun
from app.services.solver_input import remaining_demand_kg
from fastapi.testclient import TestClient
from sqlmodel import Session, select

AUTH = {"X-Access-Pin": "123456"}
OPTIMIZE_URL = "/api/v1/solver/optimize"
ORDERS_URL = "/api/v1/erp/orders"
STOCKS_URL = "/api/v1/erp/stocks"

EPSILON = 1e-6


def _database_session(client: TestClient) -> Session:
    return Session(client.app.state.db_engine)  # type: ignore[attr-defined]


@pytest.fixture
def baseline(client: TestClient) -> dict:
    response = client.post(OPTIMIZE_URL, headers=AUTH, json={"mode": "baseline"})
    assert response.status_code == 200
    return response.json()


def _planned_kg_by_warehouse(routes: list[dict], order_id: int) -> dict[int, float]:
    planned: dict[int, float] = {}
    for route in routes:
        for stop in route["stops"]:
            if stop["order_id"] == order_id:
                planned[stop["warehouse_id"]] = (
                    planned.get(stop["warehouse_id"], 0.0) + stop["shipped_kg"]
                )
    return planned


def test_delivered_order_consumes_stock_and_leaves_new_plan(client: TestClient) -> None:
    baseline = client.post(OPTIMIZE_URL, headers=AUTH, json={"mode": "baseline"}).json()
    order_id = baseline["routes"][0]["stops"][0]["order_id"]
    planned = _planned_kg_by_warehouse(baseline["routes"], order_id)
    assert planned

    with _database_session(client) as session:
        order = session.get(ClientOrder, order_id)
        assert order is not None
        product_id = order.product_id
        requested_kg = order.requested_kg
        stock_before = sum(
            stock.available_kg
            for stock in session.exec(
                select(WarehouseStock).where(WarehouseStock.product_id == product_id)
            ).all()
        )

    response = client.patch(
        f"{ORDERS_URL}/{order_id}",
        headers=AUTH,
        json={"delivery_status": "delivered"},
    )
    assert response.status_code == 200
    assert response.json()["delivery_status"] == "delivered"
    assert response.json()["delivered_kg"] == pytest.approx(requested_kg)

    with _database_session(client) as session:
        stock_after = sum(
            stock.available_kg
            for stock in session.exec(
                select(WarehouseStock).where(WarehouseStock.product_id == product_id)
            ).all()
        )
        journal = session.exec(
            select(DeliveredOrderStock).where(DeliveredOrderStock.order_id == order_id)
        ).all()
        for warehouse_id, shipped_kg in planned.items():
            stock = session.exec(
                select(WarehouseStock).where(
                    WarehouseStock.product_id == product_id,
                    WarehouseStock.warehouse_id == warehouse_id,
                )
            ).one()
            entry = next(item for item in journal if item.stock_id == stock.id)
            assert entry.shipped_kg == pytest.approx(shipped_kg)

    assert stock_before - stock_after == pytest.approx(sum(planned.values()))
    assert sum(entry.shipped_kg for entry in journal) == pytest.approx(sum(planned.values()))

    what_if = client.post(
        OPTIMIZE_URL,
        headers=AUTH,
        json={"mode": "what_if", "baseline_run_id": baseline["run_id"]},
    ).json()
    shipped_ids = {stop["order_id"] for route in what_if["routes"] for stop in route["stops"]}
    assert order_id not in shipped_ids
    assert what_if["metrics"]["shipped_kg"] <= baseline["metrics"]["shipped_kg"]


def test_partial_plan_keeps_leftover_demand_and_reports_delivered_kg(
    client: TestClient,
) -> None:
    with _database_session(client) as session:
        order = session.get(ClientOrder, 1)
        truck = session.exec(select(Truck).order_by(Truck.id)).first()
        stock = session.exec(
            select(WarehouseStock).where(
                WarehouseStock.product_id == order.product_id,
                WarehouseStock.warehouse_id == truck.warehouse_id,
            )
        ).one()
        stock.available_kg = 500.0
        run = SimulationRun()
        session.add(run)
        session.commit()
        session.refresh(run)
        session.add(
            RouteStop(
                run_id=int(run.id or 0),
                order_id=order.id,
                truck_id=int(truck.id or 0),
                warehouse_id=truck.warehouse_id,
                client_id=order.client_id,
                product_id=order.product_id,
                sequence_order=1,
                shipped_kg=500.0,
            )
        )
        session.commit()
        requested_kg = order.requested_kg
        order_id = int(order.id or 0)
        product_id = order.product_id
        consumed_warehouse_id = truck.warehouse_id
        stock_before = sum(
            item.available_kg
            for item in session.exec(
                select(WarehouseStock).where(WarehouseStock.product_id == product_id)
            ).all()
        )

    response = client.patch(
        f"{ORDERS_URL}/{order_id}",
        headers=AUTH,
        json={"delivery_status": "delivered"},
    )

    assert response.status_code == 200
    assert response.json()["delivery_status"] == "pending"
    assert response.json()["delivered_kg"] == pytest.approx(500.0)

    with _database_session(client) as session:
        reloaded = session.get(ClientOrder, order_id)
        assert reloaded is not None
        assert remaining_demand_kg(reloaded) == pytest.approx(requested_kg - 500.0)
        stock_total = sum(
            item.available_kg
            for item in session.exec(
                select(WarehouseStock).where(WarehouseStock.product_id == product_id)
            ).all()
        )
        consumed_stock = session.exec(
            select(WarehouseStock).where(
                WarehouseStock.product_id == product_id,
                WarehouseStock.warehouse_id == consumed_warehouse_id,
            )
        ).one()

    assert stock_before - stock_total == pytest.approx(500.0)
    assert consumed_stock.available_kg == pytest.approx(0.0)

    plan = client.post(OPTIMIZE_URL, headers=AUTH, json={"mode": "baseline"}).json()
    replanned = _planned_kg_by_warehouse(plan["routes"], order_id)
    assert 500.0 + sum(replanned.values()) <= requested_kg + EPSILON


def test_partial_delivery_can_be_rolled_back_with_pending_status(client: TestClient) -> None:
    with _database_session(client) as session:
        order = session.get(ClientOrder, 1)
        truck = session.exec(select(Truck).order_by(Truck.id)).first()
        stock = session.exec(
            select(WarehouseStock).where(
                WarehouseStock.product_id == order.product_id,
                WarehouseStock.warehouse_id == truck.warehouse_id,
            )
        ).one()
        stock.available_kg = 500.0
        run = SimulationRun()
        session.add(run)
        session.commit()
        session.refresh(run)
        session.add(
            RouteStop(
                run_id=int(run.id or 0),
                order_id=order.id,
                truck_id=int(truck.id or 0),
                warehouse_id=truck.warehouse_id,
                client_id=order.client_id,
                product_id=order.product_id,
                sequence_order=1,
                shipped_kg=500.0,
            )
        )
        session.commit()
        order_id = int(order.id or 0)
        product_id = order.product_id
        warehouse_id = truck.warehouse_id

    client.patch(f"{ORDERS_URL}/{order_id}", headers=AUTH, json={"delivery_status": "delivered"})
    response = client.patch(
        f"{ORDERS_URL}/{order_id}",
        headers=AUTH,
        json={"delivery_status": "pending"},
    )

    assert response.status_code == 200
    assert response.json()["delivered_kg"] == 0.0

    with _database_session(client) as session:
        journal = session.exec(
            select(DeliveredOrderStock).where(DeliveredOrderStock.order_id == order_id)
        ).all()
        restored = session.exec(
            select(WarehouseStock).where(
                WarehouseStock.product_id == product_id,
                WarehouseStock.warehouse_id == warehouse_id,
            )
        ).one()

    assert journal == []
    assert restored.available_kg == pytest.approx(500.0)


def test_switching_back_to_pending_restores_stock_and_demand(client: TestClient) -> None:
    baseline = client.post(OPTIMIZE_URL, headers=AUTH, json={"mode": "baseline"}).json()
    order_id = baseline["routes"][0]["stops"][0]["order_id"]

    with _database_session(client) as session:
        order = session.get(ClientOrder, order_id)
        product_id = order.product_id
        stock_before = sum(
            stock.available_kg
            for stock in session.exec(
                select(WarehouseStock).where(WarehouseStock.product_id == product_id)
            ).all()
        )

    client.patch(f"{ORDERS_URL}/{order_id}", headers=AUTH, json={"delivery_status": "delivered"})
    restored = client.patch(
        f"{ORDERS_URL}/{order_id}",
        headers=AUTH,
        json={"delivery_status": "pending"},
    )

    assert restored.status_code == 200
    assert restored.json()["delivered_kg"] == 0.0
    assert restored.json()["delivery_status"] == "pending"

    with _database_session(client) as session:
        stock_after = sum(
            stock.available_kg
            for stock in session.exec(
                select(WarehouseStock).where(WarehouseStock.product_id == product_id)
            ).all()
        )
        journal = session.exec(
            select(DeliveredOrderStock).where(DeliveredOrderStock.order_id == order_id)
        ).all()

    assert stock_after == pytest.approx(stock_before)
    assert journal == []


def test_delivery_conflicts_when_stock_changed_after_the_plan(client: TestClient) -> None:
    baseline = client.post(OPTIMIZE_URL, headers=AUTH, json={"mode": "baseline"}).json()
    order_id = baseline["routes"][0]["stops"][0]["order_id"]

    with _database_session(client) as session:
        order = session.get(ClientOrder, order_id)
        stock = session.exec(
            select(WarehouseStock).where(WarehouseStock.product_id == order.product_id)
        ).first()

    client.patch(f"{STOCKS_URL}/{stock.id}", headers=AUTH, json={"available_kg": 0.0})
    response = client.patch(
        f"{ORDERS_URL}/{order_id}",
        headers=AUTH,
        json={"delivery_status": "delivered"},
    )

    assert response.status_code == 409
    assert response.json()["code"] == "conflict"


def test_delivery_without_any_plan_is_closed_as_delivered(client: TestClient) -> None:
    response = client.patch(
        f"{ORDERS_URL}/1",
        headers=AUTH,
        json={"delivery_status": "delivered"},
    )

    assert response.status_code == 200
    assert response.json()["delivery_status"] == "delivered"

    with _database_session(client) as session:
        assert session.exec(select(DeliveredOrderStock)).all() == []

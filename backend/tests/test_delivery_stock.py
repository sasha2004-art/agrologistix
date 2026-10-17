"""Delivery accounting: stock write-off, partial deliveries and leftover demand."""

import pytest
from app.models.erp_models import ClientOrder, Truck, WarehouseStock
from app.models.run_models import DeliveredOrderStock, RouteStop, SimulationRun
from app.services.solver_input import remaining_demand_kg
from fastapi.testclient import TestClient
from sqlmodel import Session, select

AUTH = {"X-Access-Pin": "123456"}
ADMIN_AUTH = {"X-Access-Pin": "654321"}
OPTIMIZE_URL = "/api/v1/solver/optimize"
ORDERS_URL = "/api/v1/erp/orders"
STOCKS_URL = "/api/v1/erp/stocks"
RESET_URL = "/api/v1/system/reset-demo"

EPSILON = 1e-6


def _database_session(client: TestClient) -> Session:
    return Session(client.app.state.db_engine)  # type: ignore[attr-defined]


@pytest.fixture
def baseline(client: TestClient) -> dict:
    response = client.post(OPTIMIZE_URL, headers=AUTH, json={})
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
    baseline = client.post(OPTIMIZE_URL, headers=AUTH, json={}).json()
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

    # A fresh plan built from the current ERP state must not ship the delivered
    # order again and can only move the remaining demand.
    replanned = client.post(OPTIMIZE_URL, headers=AUTH, json={}).json()
    shipped_ids = {stop["order_id"] for route in replanned["routes"] for stop in route["stops"]}
    assert order_id not in shipped_ids
    assert replanned["metrics"]["shipped_kg"] <= baseline["metrics"]["shipped_kg"]


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

    plan = client.post(OPTIMIZE_URL, headers=AUTH, json={}).json()
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
    baseline = client.post(OPTIMIZE_URL, headers=AUTH, json={}).json()
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
    baseline = client.post(OPTIMIZE_URL, headers=AUTH, json={}).json()
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


def test_reset_demo_clears_delivered_stock_journal(client: TestClient) -> None:
    baseline = client.post(OPTIMIZE_URL, headers=AUTH, json={}).json()
    order_id = baseline["routes"][0]["stops"][0]["order_id"]
    assert (
        client.patch(
            f"{ORDERS_URL}/{order_id}",
            headers=AUTH,
            json={"delivery_status": "delivered"},
        ).status_code
        == 200
    )

    with _database_session(client) as session:
        assert session.exec(select(DeliveredOrderStock)).all() != []

    reset = client.post(RESET_URL, headers=ADMIN_AUTH)

    assert reset.status_code == 200
    with _database_session(client) as session:
        assert session.exec(select(DeliveredOrderStock)).all() == []
        assert session.get(ClientOrder, order_id).delivered_kg == 0.0
        assert session.get(ClientOrder, order_id).delivery_status == "pending"
        assert session.exec(select(RouteStop)).all() == []
        assert session.exec(select(SimulationRun)).all() == []


def test_delivery_uses_the_latest_plan_and_truncates_it_to_the_leftover(
    client: TestClient,
) -> None:
    with _database_session(client) as session:
        order = session.get(ClientOrder, 1)
        truck = session.exec(select(Truck).order_by(Truck.id)).first()
        old_run = SimulationRun()
        new_run = SimulationRun()
        session.add(old_run)
        session.add(new_run)
        session.commit()
        session.refresh(old_run)
        session.refresh(new_run)
        base_stop = {
            "order_id": order.id,
            "truck_id": truck.id,
            "client_id": order.client_id,
            "product_id": order.product_id,
            "sequence_order": 1,
        }
        # The old plan ships 1000 kg from the second warehouse.
        session.add(
            RouteStop(
                run_id=int(old_run.id or 0),
                warehouse_id=2,
                shipped_kg=1000.0,
                **base_stop,
            )
        )
        # The latest plan ships 1000 kg from warehouse 1 and 1000 kg from 2;
        # the order was already partially delivered (500 kg left), so only the
        # first warehouse entry is written off and the loop stops early.
        session.add(
            RouteStop(
                run_id=int(new_run.id or 0),
                warehouse_id=1,
                shipped_kg=1000.0,
                **base_stop,
            )
        )
        session.add(
            RouteStop(
                run_id=int(new_run.id or 0),
                warehouse_id=2,
                shipped_kg=1000.0,
                sequence_order=2,
                **{key: value for key, value in base_stop.items() if key != "sequence_order"},
            )
        )
        order.delivered_kg = order.requested_kg - 500.0
        session.add(order)
        session.commit()
        requested_kg = order.requested_kg
        order_id = int(order.id or 0)

    response = client.patch(
        f"{ORDERS_URL}/{order_id}",
        headers=AUTH,
        json={"delivery_status": "delivered"},
    )

    assert response.status_code == 200
    assert response.json()["delivered_kg"] == pytest.approx(requested_kg)

    with _database_session(client) as session:
        journal = session.exec(
            select(DeliveredOrderStock).where(DeliveredOrderStock.order_id == order_id)
        ).all()
        stocks = session.exec(
            select(WarehouseStock).where(WarehouseStock.product_id == order.product_id)
        ).all()

    by_warehouse = {entry.stock_id: entry.shipped_kg for entry in journal}
    assert len(by_warehouse) == 1
    assert sum(by_warehouse.values()) == pytest.approx(500.0)
    warehouse_one = next(stock for stock in stocks if stock.warehouse_id == 1)
    assert warehouse_one.available_kg == pytest.approx(9000.0 - 500.0)


def test_delivery_ignores_stops_of_another_product(client: TestClient) -> None:
    with _database_session(client) as session:
        order = session.get(ClientOrder, 1)
        truck = session.exec(select(Truck).order_by(Truck.id)).first()
        run = SimulationRun()
        session.add(run)
        session.commit()
        session.refresh(run)
        common = {
            "run_id": int(run.id or 0),
            "order_id": order.id,
            "truck_id": truck.id,
            "warehouse_id": 1,
            "client_id": order.client_id,
        }
        session.add(
            RouteStop(
                sequence_order=1,
                product_id=1 if order.product_id != 1 else 2,
                shipped_kg=999.0,
                **common,
            )
        )
        session.add(
            RouteStop(
                sequence_order=2,
                product_id=order.product_id,
                shipped_kg=order.requested_kg,
                **common,
            )
        )
        session.commit()
        order_id = int(order.id or 0)
        requested_kg = order.requested_kg

    response = client.patch(
        f"{ORDERS_URL}/{order_id}",
        headers=AUTH,
        json={"delivery_status": "delivered"},
    )

    assert response.status_code == 200
    assert response.json()["delivered_kg"] == pytest.approx(requested_kg)
    with _database_session(client) as session:
        journal = session.exec(
            select(DeliveredOrderStock).where(DeliveredOrderStock.order_id == order_id)
        ).all()
    assert sum(entry.shipped_kg for entry in journal) == pytest.approx(requested_kg)


def test_repeated_delivery_fixation_does_not_write_off_stock_twice(client: TestClient) -> None:
    with _database_session(client) as session:
        order = session.get(ClientOrder, 1)
        order.delivered_kg = order.requested_kg
        order.delivery_status = "pending"
        session.add(order)
        session.commit()
        order_id = int(order.id or 0)
        requested_kg = order.requested_kg
        stock_before = sum(
            stock.available_kg
            for stock in session.exec(
                select(WarehouseStock).where(WarehouseStock.product_id == order.product_id)
            ).all()
        )

    response = client.patch(
        f"{ORDERS_URL}/{order_id}",
        headers=AUTH,
        json={"delivery_status": "delivered"},
    )

    assert response.status_code == 200
    assert response.json()["delivered_kg"] == pytest.approx(requested_kg)
    with _database_session(client) as session:
        assert session.exec(select(DeliveredOrderStock)).all() == []
        stock_after = sum(
            stock.available_kg
            for stock in session.exec(
                select(WarehouseStock).where(WarehouseStock.product_id == order.product_id)
            ).all()
        )
    assert stock_after == pytest.approx(stock_before)


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

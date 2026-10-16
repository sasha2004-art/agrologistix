from app.models.erp_models import ClientOrder, Product, Truck, Warehouse, WarehouseStock
from app.services.seed_kaluga import reset_demo_database, seed_database
from sqlmodel import Session, select

EXPECTED_COUNTS = {
    "warehouses": 2,
    "products": 3,
    "stocks": 6,
    "clients": 5,
    "orders": 9,
    "trucks": 3,
}


def test_seed_populates_kaluga_reference_data(session: Session) -> None:
    summary = seed_database(session)

    assert summary.seeded is True
    assert summary.warehouses == EXPECTED_COUNTS["warehouses"]
    assert summary.products == EXPECTED_COUNTS["products"]
    assert summary.stocks == EXPECTED_COUNTS["stocks"]
    assert summary.clients == EXPECTED_COUNTS["clients"]
    assert summary.orders == EXPECTED_COUNTS["orders"]
    assert summary.trucks == EXPECTED_COUNTS["trucks"]


def test_seed_is_idempotent(session: Session) -> None:
    first = seed_database(session)
    second = seed_database(session)

    assert first.seeded is True
    assert second.seeded is False
    assert second.warehouses == first.warehouses
    assert second.orders == first.orders
    assert len(session.exec(select(Warehouse)).all()) == EXPECTED_COUNTS["warehouses"]


def test_seed_contains_dirt_road_and_reefer_variety(session: Session) -> None:
    seed_database(session)
    trucks = list(session.exec(select(Truck)).all())

    assert len({truck.plate_number for truck in trucks}) == EXPECTED_COUNTS["trucks"]
    assert any(truck.has_reefer and not truck.can_use_dirt for truck in trucks)
    assert any(truck.has_reefer and truck.can_use_dirt for truck in trucks)
    assert any(not truck.has_reefer and truck.can_use_dirt for truck in trucks)
    assert sum(1 for truck in trucks if truck.can_use_dirt) == 2


def test_single_client_can_hold_several_orders(session: Session) -> None:
    seed_database(session)

    orders = session.exec(select(ClientOrder)).all()
    client_orders: dict[int, int] = {}
    for order in orders:
        client_orders[order.client_id] = client_orders.get(order.client_id, 0) + 1

    assert max(client_orders.values()) >= 2


def test_reset_demo_restores_original_state(session: Session) -> None:
    seed_database(session)
    order = session.exec(select(ClientOrder)).first()
    assert order is not None and order.id is not None
    order_id = order.id

    order.purchase_price_rub = 1.0
    order.delivery_status = "delivered"
    session.add(order)
    session.commit()
    session.expunge_all()

    summary = reset_demo_database(session)
    restored = session.get(ClientOrder, order_id)

    assert summary.seeded is True
    assert restored is not None
    assert restored.purchase_price_rub > 1.0
    assert restored.delivery_status == "pending"
    assert len(session.exec(select(WarehouseStock)).all()) == EXPECTED_COUNTS["stocks"]
    assert len(session.exec(select(Product)).all()) == EXPECTED_COUNTS["products"]

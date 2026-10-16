import pytest
from app.models.erp_models import Client, ClientOrder, Truck, WarehouseStock
from app.services.seed_kaluga import seed_database
from sqlalchemy.exc import IntegrityError
from sqlmodel import Session


def test_truck_capacity_must_be_positive(session: Session) -> None:
    seed_database(session)
    session.add(
        Truck(
            name="Broken capacity",
            plate_number="X000XX00",
            warehouse_id=1,
            capacity_kg=-1.0,
            cruise_speed_kmh=60.0,
            cost_per_km_rub=30.0,
            fixed_trip_cost_rub=1000.0,
        )
    )

    with pytest.raises(IntegrityError):
        session.commit()
    session.rollback()


def test_order_requested_kg_must_be_positive(session: Session) -> None:
    seed_database(session)
    session.add(
        ClientOrder(
            client_id=1,
            product_id=1,
            requested_kg=0.0,
            purchase_price_rub=100.0,
            unmet_penalty_rub=10.0,
        )
    )

    with pytest.raises(IntegrityError):
        session.commit()
    session.rollback()


def test_stock_pair_must_be_unique(session: Session) -> None:
    seed_database(session)
    session.add_all(
        [
            WarehouseStock(warehouse_id=1, product_id=1, available_kg=100.0),
            WarehouseStock(warehouse_id=1, product_id=1, available_kg=200.0),
        ]
    )

    with pytest.raises(IntegrityError):
        session.commit()
    session.rollback()


def test_client_road_type_is_restricted(session: Session) -> None:
    session.add(
        Client(
            name="Unknown road",
            lat=55.0,
            lon=36.0,
            road_type="highway",
        )
    )

    with pytest.raises(IntegrityError):
        session.commit()
    session.rollback()

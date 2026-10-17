"""Tests for building the solver input from the persisted ERP state."""

import asyncio
from collections.abc import Iterator
from datetime import UTC, datetime
from pathlib import Path

import pytest
from app.core.config import Settings
from app.core.database import create_database_engine, init_database
from app.models.erp_models import Client, ClientOrder
from app.schemas.enums import DeliveryStatus, WeatherMode
from app.services.seed_kaluga import seed_database
from app.services.solver_input import SolverInput, build_solver_input, remaining_demand_kg
from app.services.weather_service import WeatherSnapshot
from sqlmodel import Session, select

TARUSA = (54.72, 37.18)
BOROVSK = (55.2075, 36.4850)


@pytest.fixture
def session(tmp_path: Path) -> Iterator[Session]:
    settings = Settings(sqlite_db_path=str(tmp_path / "input.db"))
    engine = create_database_engine(settings)
    init_database(engine)
    with Session(engine) as database_session:
        seed_database(database_session)
        yield database_session
    engine.dispose()


def _weather() -> WeatherSnapshot:
    return WeatherSnapshot(
        temperature_c=20.0,
        precipitation_mm=0.0,
        weather_code=1,
        mode=WeatherMode.NORMAL,
        fetched_at=datetime.now(UTC),
    )


def _order(session: Session, order_id: int) -> ClientOrder:
    order = session.get(ClientOrder, order_id)
    assert order is not None
    return order


def _build(session: Session) -> SolverInput:
    return asyncio.run(build_solver_input(session, Settings(sqlite_db_path=":memory:"), _weather()))


def _leg_points(solver_input: SolverInput) -> set[tuple[float, float]]:
    return {leg.origin for leg in solver_input.legs} | {
        leg.destination for leg in solver_input.legs
    }


def test_delivered_order_point_is_not_resolved(session: Session) -> None:
    client = session.exec(select(Client).where(Client.address.like("%Таруса%"))).one()
    tarusa_order = _order(session, 9)
    assert tarusa_order.client_id == client.id

    before = _build(session)
    assert (client.lat, client.lon) in _leg_points(before)
    assert TARUSA in _leg_points(before)

    tarusa_order.delivery_status = DeliveryStatus.DELIVERED.value
    session.add(tarusa_order)
    session.commit()

    after = _build(session)
    assert TARUSA not in _leg_points(after)
    assert all(order.order_id != 9 for order in after.orders)


def test_partially_delivered_order_keeps_only_the_leftover_demand(session: Session) -> None:
    order = _order(session, 1)
    order.delivered_kg = 150.0
    session.add(order)
    session.commit()

    solver_input = _build(session)

    planned = next(item for item in solver_input.orders if item.order_id == 1)
    assert planned.requested_kg == pytest.approx(order.requested_kg - 150.0)
    assert remaining_demand_kg(order) == pytest.approx(250.0)


def test_dirt_order_distance_is_present_for_offroad_clients(session: Session) -> None:
    solver_input = _build(session)

    borovsk = next(order for order in solver_input.orders if order.client_id == 3)
    assert (borovsk.latitude, borovsk.longitude) == BOROVSK
    assert any(leg.destination == BOROVSK for leg in solver_input.legs)


def test_frozen_orders_are_never_planned(session: Session) -> None:
    order = _order(session, 5)
    order.delivery_status = DeliveryStatus.DELIVERED.value
    order.delivered_kg = order.requested_kg
    session.add(order)
    session.commit()

    solver_input = _build(session)

    assert 5 in solver_input.frozen_order_ids
    assert all(item.order_id != 5 for item in solver_input.orders)

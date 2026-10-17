"""Integration tests: the solver engine on the real Kaluga seed dataset."""

import asyncio
from collections.abc import Iterator
from datetime import UTC, datetime
from pathlib import Path

import pytest
from app.core.config import Settings
from app.core.database import create_database_engine, init_database
from app.models.erp_models import Client, ClientOrder, Truck, WarehouseStock
from app.schemas.enums import DeliveryStatus, RoadType, TruckStatus, WeatherMode
from app.services.seed_kaluga import seed_database
from app.services.solver_engine import run_solver
from app.services.solver_input import build_solver_input
from app.services.solver_mapper import to_solver_response
from app.services.weather_service import WeatherSnapshot
from sqlmodel import Session, select


@pytest.fixture
def session(tmp_path: Path) -> Iterator[Session]:
    settings = Settings(sqlite_db_path=str(tmp_path / "solver.db"))
    engine = create_database_engine(settings)
    init_database(engine)
    with Session(engine) as database_session:
        seed_database(database_session)
        yield database_session
    engine.dispose()


def _weather(temperature_c: float = 20.0, precipitation_mm: float = 0.0) -> WeatherSnapshot:
    return WeatherSnapshot(
        temperature_c=temperature_c,
        precipitation_mm=precipitation_mm,
        weather_code=1,
        mode=WeatherMode.NORMAL,
        fetched_at=datetime.now(UTC),
    )


def _solve(session: Session, weather: WeatherSnapshot | None = None):
    settings = Settings(sqlite_db_path=":memory:")
    solver_input = asyncio.run(build_solver_input(session, settings, weather or _weather()))
    return run_solver(solver_input)


def test_seed_dataset_produces_a_plan(session: Session) -> None:
    outcome = _solve(session)

    assert outcome.routes
    assert outcome.metrics.shipped_kg > 0
    assert outcome.metrics.total_trip_cost_rub > 0
    assert outcome.allocation_method == "milp"
    assert outcome.elapsed_ms < 1500.0


def test_every_pending_order_is_shipped_or_unmet(session: Session) -> None:
    outcome = _solve(session)

    orders = session.exec(select(ClientOrder)).all()
    requested_total = sum(
        order.requested_kg for order in orders if order.delivery_status == DeliveryStatus.PENDING
    )

    assert outcome.metrics.shipped_kg + outcome.metrics.unmet_kg == pytest.approx(
        requested_total,
        abs=0.05,
    )


def test_capacity_and_stock_limits_hold_on_seed_data(session: Session) -> None:
    outcome = _solve(session)
    trucks = {truck.id: truck for truck in session.exec(select(Truck)).all()}
    stocks = {
        (stock.warehouse_id, stock.product_id): stock.available_kg
        for stock in session.exec(select(WarehouseStock)).all()
    }

    shipped_by_stock: dict[tuple[int, int], float] = {}
    for route in outcome.routes:
        truck = trucks[route.truck_id]
        assert sum(stop.shipped_kg for stop in route.stops) <= truck.capacity_kg + 1e-6
        for stop in route.stops:
            key = (truck.warehouse_id, stop.product_id)
            shipped_by_stock[key] = shipped_by_stock.get(key, 0.0) + stop.shipped_kg

    for key, shipped in shipped_by_stock.items():
        assert shipped <= stocks[key] + 1e-6


def test_dirt_clients_are_served_only_by_offroad_trucks(session: Session) -> None:
    outcome = _solve(session)
    clients = {client.id: client for client in session.exec(select(Client)).all()}
    trucks = {truck.id: truck for truck in session.exec(select(Truck)).all()}

    for route in outcome.routes:
        for stop in route.stops:
            if clients[stop.client_id].road_type == RoadType.DIRT:
                assert trucks[route.truck_id].can_use_dirt is True


def test_heatwave_stress_without_reefers_stays_feasible(session: Session) -> None:
    """PRD scenario: heat +35 C and every reefer truck broken."""

    for truck in session.exec(select(Truck)).all():
        if truck.has_reefer:
            truck.status = TruckStatus.BROKEN.value
            session.add(truck)
    session.commit()

    outcome = _solve(session, _weather(temperature_c=35.0))

    codes = {warning.code for warning in outcome.warnings}
    assert {"heat_without_reefer", "broken_trucks_excluded"} <= codes
    assert outcome.metrics.shipped_kg > 0
    assert outcome.metrics.avg_freshness_pct < 100.0


def test_delivered_order_is_frozen_and_ignored(session: Session) -> None:
    order = session.exec(select(ClientOrder).where(ClientOrder.client_id == 3)).first()
    assert order is not None
    order.delivery_status = DeliveryStatus.DELIVERED.value
    session.add(order)
    session.commit()

    outcome = _solve(session)
    shipped_order_ids = {stop.order_id for route in outcome.routes for stop in route.stops}

    assert order.id not in shipped_order_ids
    assert outcome.metrics.unmet_kg < sum(
        item.requested_kg
        for item in session.exec(select(ClientOrder)).all()
        if item.delivery_status == DeliveryStatus.PENDING
    )


def test_outcome_maps_to_the_public_solver_response(session: Session) -> None:
    outcome = _solve(session)

    response = to_solver_response(outcome, run_id=1)
    payload = response.model_dump(mode="json")

    assert payload["run_id"] == 1
    assert payload["metrics"]["shipped_kg"] == outcome.metrics.shipped_kg
    assert payload["routes"][0]["stops"][0]["sequence_order"] == 1
    assert payload["routes"][0]["geometry"][0]["lat"] is not None
    assert response.model_dump_json()


def test_all_trucks_broken_stays_feasible(session: Session) -> None:
    for truck in session.exec(select(Truck)).all():
        truck.status = TruckStatus.BROKEN.value
        session.add(truck)
    session.commit()

    outcome = _solve(session)

    assert outcome.routes == ()
    assert outcome.metrics.unmet_kg > 0
    assert outcome.metrics.shipped_kg == 0.0
    codes = {warning.code for warning in outcome.warnings}
    assert {"no_active_trucks", "unmet_demand"} <= codes

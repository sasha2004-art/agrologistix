"""Greedy fallback and degenerate-input tests for the allocation layer."""

import asyncio
from datetime import UTC, datetime

import pytest
from app.core.config import Settings
from app.core.database import create_database_engine, init_database
from app.models.erp_models import Warehouse
from app.schemas.enums import RoadType, WarningSeverity, WeatherMode
from app.services import solver_allocation
from app.services.seed_kaluga import seed_database
from app.services.solver_engine import run_solver
from app.services.solver_input import build_solver_input
from app.services.weather_service import WeatherSnapshot
from sqlmodel import Session, select
from tests.solver_factory import (
    BOROVSK,
    DETCHINO as DETCHINO_POINT,
    OBININSK as OBININSK_POINT,
    _make_input,
    _order,
    _stock,
    _truck,
    _warehouse,
)


class _NoSolution:
    """Mimics ``scipy.optimize.milp`` when it cannot find a feasible point."""

    x = None
    status = 2
    message = "time limit reached"


def _boom(**_kwargs: object) -> object:
    raise RuntimeError("HiGHS crashed on degenerate input")


def test_milp_without_solution_falls_back_to_greedy(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(solver_allocation, "milp", lambda **_kwargs: _NoSolution())
    solver_input = _make_input(
        orders=[_order(1, kg=1000.0)],
        trucks=[_truck(capacity=800.0)],
    )

    outcome = run_solver(solver_input)

    assert outcome.allocation_method.startswith("greedy")
    assert outcome.metrics.shipped_kg == pytest.approx(800.0, abs=0.01)
    assert outcome.metrics.unmet_kg == pytest.approx(200.0, abs=0.01)


def test_milp_exception_falls_back_to_greedy(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(solver_allocation, "milp", _boom)
    solver_input = _make_input(
        orders=[_order(1, kg=600.0)],
        trucks=[_truck(capacity=1000.0)],
    )

    outcome = run_solver(solver_input)

    assert outcome.allocation_method.startswith("greedy")
    assert outcome.metrics.shipped_kg == pytest.approx(600.0, abs=0.01)
    assert outcome.metrics.unmet_kg == pytest.approx(0.0, abs=0.01)


def test_greedy_serves_the_most_valuable_order_first(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(solver_allocation, "milp", lambda **_kwargs: _NoSolution())
    cheap = _order(1, kg=500.0, price=100.0, penalty=10.0)
    valuable = _order(2, client_id=2, kg=500.0, price=400.0, penalty=300.0, point=BOROVSK)
    solver_input = _make_input(orders=[cheap, valuable], trucks=[_truck(capacity=500.0)])

    outcome = run_solver(solver_input)

    shipped_orders = {
        stop.order_id for route in outcome.routes for stop in route.stops if stop.shipped_kg > 0
    }
    assert outcome.allocation_method.startswith("greedy")
    assert shipped_orders == {2}
    assert outcome.metrics.unmet_kg == pytest.approx(500.0, abs=0.01)


def test_greedy_fallback_respects_stock_and_capacity(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(solver_allocation, "milp", _boom)
    solver_input = _make_input(
        orders=[_order(1, kg=900.0), _order(2, client_id=2, kg=900.0, point=BOROVSK)],
        trucks=[_truck(1, capacity=1000.0), _truck(2, capacity=1000.0)],
        stocks=[_stock(kg=1200.0)],
    )

    outcome = run_solver(solver_input)

    assert outcome.allocation_method.startswith("greedy")
    assert outcome.metrics.shipped_kg <= 1200.0 + 1e-6
    for route in outcome.routes:
        assert sum(stop.shipped_kg for stop in route.stops) <= 1000.0 + 1e-6


def test_milp_returns_none_without_trucks() -> None:
    solver_input = _make_input(orders=[_order(1)], trucks=[_truck()])
    origins = {
        warehouse.warehouse_id: (warehouse.latitude, warehouse.longitude)
        for warehouse in solver_input.warehouses
    }
    products = solver_allocation._products_by_id(solver_input.products)
    stocks = solver_allocation._stocks_by_key(solver_input.stocks)
    index = solver_allocation.LegIndex(solver_input.legs)

    result = solver_allocation._milp_allocate(
        solver_input,
        list(solver_input.orders),
        [],
        products,
        stocks,
        origins,
        index,
        1.0,
        strict_grouping=True,
        split_penalty_rub=0.0,
    )

    assert result is None


def test_greedy_skips_trucks_without_stock(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(solver_allocation, "milp", lambda **_kwargs: _NoSolution())
    order = _order(1, kg=400.0, product_id=2)
    solver_input = _make_input(
        orders=[order],
        trucks=[_truck(1, warehouse_id=1), _truck(2, warehouse_id=2)],
        stocks=[_stock(warehouse_id=1, product_id=1, kg=1000.0)],
        warehouses=[
            _warehouse(1, OBININSK_POINT),
            _warehouse(2, DETCHINO_POINT),
        ],
    )

    outcome = run_solver(solver_input)

    assert outcome.allocation_method.startswith("greedy")
    assert outcome.routes == ()
    assert outcome.metrics.unmet_kg == pytest.approx(400.0, abs=0.01)


def test_dirt_order_without_offroad_truck_is_reported_unreachable() -> None:
    solver_input = _make_input(
        orders=[_order(1, kg=500.0, road_type=RoadType.DIRT, point=BOROVSK)],
        trucks=[_truck(dirt=False)],
    )

    outcome = run_solver(solver_input)

    codes = {warning.code for warning in outcome.warnings}
    unreachable = next(
        warning for warning in outcome.warnings if warning.code == "dirt_unreachable"
    )
    assert outcome.routes == ()
    assert outcome.metrics.unmet_kg == pytest.approx(500.0, abs=0.01)
    assert unreachable.order_id == 1
    assert unreachable.severity == WarningSeverity.ERROR.value
    assert "unmet_demand" in codes


def test_no_usable_truck_marks_everything_unmet() -> None:
    solver_input = _make_input(
        orders=[_order(1, kg=700.0), _order(2, client_id=2, kg=300.0, point=BOROVSK)],
        trucks=[],
    )

    outcome = run_solver(solver_input)

    assert outcome.routes == ()
    assert outcome.metrics.shipped_kg == 0.0
    assert outcome.metrics.unmet_kg == pytest.approx(1000.0, abs=0.01)
    assert "no_active_trucks" in {warning.code for warning in outcome.warnings}


def test_stock_of_inactive_warehouse_is_ignored(tmp_path) -> None:
    settings = Settings(sqlite_db_path=str(tmp_path / "inactive.db"))
    engine = create_database_engine(settings)
    init_database(engine)
    with Session(engine) as session:
        seed_database(session)
        detchino = next(
            warehouse
            for warehouse in session.exec(
                select(Warehouse).where(Warehouse.name == "Склад Детчино")
            ).all()
        )
        detchino.is_active = False
        session.add(detchino)
        session.commit()

        weather = WeatherSnapshot(
            temperature_c=20.0,
            precipitation_mm=0.0,
            weather_code=1,
            mode=WeatherMode.NORMAL,
            fetched_at=datetime.now(UTC),
        )
        solver_input = asyncio.run(build_solver_input(session, settings, weather))

    engine.dispose()

    assert {warehouse.warehouse_id for warehouse in solver_input.warehouses} == {1}
    assert all(stock.warehouse_id == 1 for stock in solver_input.stocks)
    assert len(solver_input.stocks) == 3
    assert sum(stock.available_kg for stock in solver_input.stocks) == pytest.approx(22500.0)

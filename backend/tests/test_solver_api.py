"""API tests for POST /solver/optimize: response model and persistence."""

from time import perf_counter

import pytest
from app.models.erp_models import Truck
from app.models.run_models import RouteStop, SimulationRun
from fastapi.testclient import TestClient
from sqlmodel import Session, select

USER_PIN = "123456"
AUTH = {"X-Access-Pin": USER_PIN}
OPTIMIZE_URL = "/api/v1/solver/optimize"


def _database_session(client: TestClient) -> Session:
    return Session(client.app.state.db_engine)  # type: ignore[attr-defined]


def test_optimize_requires_access_pin(client: TestClient) -> None:
    response = client.post(OPTIMIZE_URL, json={})

    assert response.status_code == 401
    assert response.json()["code"] == "unauthorized"


def test_baseline_returns_full_plan_and_metrics(client: TestClient) -> None:
    response = client.post(OPTIMIZE_URL, headers=AUTH, json={})

    assert response.status_code == 200
    payload = response.json()
    assert payload["run_id"] >= 1
    assert payload["routes"]
    assert payload["metrics"]["shipped_kg"] > 0
    assert payload["metrics"]["unmet_kg"] == 0
    assert payload["metrics"]["avg_freshness_pct"] > 0

    first_route = payload["routes"][0]
    assert first_route["geometry"]
    assert first_route["stops"]
    first_stop = first_route["stops"][0]
    assert first_stop["sequence_order"] == 1
    assert first_stop["eta_minutes"] > 0
    assert 0 <= first_stop["expected_freshness"] <= 1


def test_metrics_are_consistent(client: TestClient) -> None:
    metrics = client.post(
        OPTIMIZE_URL,
        headers=AUTH,
        json={},
    ).json()["metrics"]

    assert metrics["total_tco_rub"] == pytest.approx(
        metrics["total_trip_cost_rub"]
        + metrics["total_spoilage_loss_rub"]
        + metrics["total_unmet_penalty_rub"],
        abs=0.05,
    )
    assert metrics["shipped_kg"] + metrics["unmet_kg"] > 0


def test_baseline_is_persisted_with_route_stops(client: TestClient) -> None:
    payload = client.post(OPTIMIZE_URL, headers=AUTH, json={}).json()

    with _database_session(client) as session:
        run = session.get(SimulationRun, payload["run_id"])
        stops = session.exec(select(RouteStop).where(RouteStop.run_id == payload["run_id"])).all()

    assert run is not None
    assert run.total_tco_rub == payload["metrics"]["total_tco_rub"]
    assert run.avg_freshness_pct == payload["metrics"]["avg_freshness_pct"]
    assert run.weather_mode == "normal"
    assert len(stops) == sum(len(route["stops"]) for route in payload["routes"])
    assert all(stop.stop_status == "planned" for stop in stops)
    assert {stop.truck_id for stop in stops} == {route["truck_id"] for route in payload["routes"]}


def test_repeated_calculation_creates_a_new_run(client: TestClient) -> None:
    first = client.post(OPTIMIZE_URL, headers=AUTH, json={}).json()
    second = client.post(OPTIMIZE_URL, headers=AUTH, json={}).json()

    with _database_session(client) as session:
        runs = session.exec(select(SimulationRun)).all()

    assert second["run_id"] > first["run_id"]
    assert len(runs) == 2


def test_optimize_completes_within_the_budget(client: TestClient) -> None:
    started = perf_counter()
    response = client.post(OPTIMIZE_URL, headers=AUTH, json={})
    elapsed = perf_counter() - started

    assert response.status_code == 200
    assert elapsed < 1.5


def test_weather_override_is_persisted_in_the_run(client: TestClient) -> None:
    client.post(
        "/api/v1/weather/override",
        headers=AUTH,
        json={"mode": "heatwave_35c"},
    )

    payload = client.post(OPTIMIZE_URL, headers=AUTH, json={}).json()

    with _database_session(client) as session:
        run = session.get(SimulationRun, payload["run_id"])

    assert run is not None
    assert run.weather_mode == "heatwave_35c"
    assert run.temp_c == 35.0


def test_heat_without_reefer_warning_reaches_the_api(client: TestClient) -> None:
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
    payload = client.post(OPTIMIZE_URL, headers=AUTH, json={}).json()

    codes = {warning["code"] for warning in payload["warnings"]}
    assert {"heat_without_reefer", "broken_trucks_excluded"} <= codes


def test_no_active_trucks_returns_unmet_demand(client: TestClient) -> None:
    with _database_session(client) as session:
        for truck in session.exec(select(Truck)).all():
            truck.status = "broken"
            session.add(truck)
        session.commit()

    payload = client.post(OPTIMIZE_URL, headers=AUTH, json={}).json()

    assert payload["routes"] == []
    assert payload["metrics"]["shipped_kg"] == 0
    assert payload["metrics"]["unmet_kg"] > 0
    assert "no_active_trucks" in {warning["code"] for warning in payload["warnings"]}


def test_delivered_order_is_not_reassigned(client: TestClient) -> None:
    client.patch(
        "/api/v1/erp/orders/1",
        headers=AUTH,
        json={"delivery_status": "delivered"},
    )

    payload = client.post(OPTIMIZE_URL, headers=AUTH, json={}).json()
    shipped_order_ids = {stop["order_id"] for route in payload["routes"] for stop in route["stops"]}

    assert 1 not in shipped_order_ids


def test_request_body_is_validated(client: TestClient) -> None:
    ok = client.post(OPTIMIZE_URL, headers=AUTH, json={})
    unknown_field = client.post(
        OPTIMIZE_URL,
        headers=AUTH,
        json={"trucks": []},
    )

    assert ok.status_code == 200
    assert unknown_field.status_code == 422
    assert unknown_field.json()["code"] == "validation_error"

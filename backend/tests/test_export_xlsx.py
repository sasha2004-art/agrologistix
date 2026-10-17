"""XLSX export tests: workbook structure, stored runs and error handling."""

from datetime import UTC, datetime
from io import BytesIO

import pytest
from app.models.erp_models import Truck
from app.models.run_models import SimulationRun
from app.services.xlsx_exporter import (
    ExportRoute,
    ExportRun,
    ExportStop,
    build_workbook,
)
from fastapi.testclient import TestClient
from openpyxl import load_workbook
from sqlmodel import Session, select

AUTH = {"X-Access-Pin": "123456"}
OPTIMIZE_URL = "/api/v1/solver/optimize"
EXPORT_URL = "/api/v1/export/run/{run_id}/xlsx"
XLSX_MEDIA_TYPE = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"

SUMMARY_TITLE = "Сводка"


def _database_session(client: TestClient) -> Session:
    return Session(client.app.state.db_engine)  # type: ignore[attr-defined]


def _baseline(client: TestClient) -> dict:
    response = client.post(OPTIMIZE_URL, headers=AUTH, json={})
    assert response.status_code == 200
    return response.json()


def _export(client: TestClient, run_id: int) -> bytes:
    response = client.get(EXPORT_URL.format(run_id=run_id), headers=AUTH)
    assert response.status_code == 200
    assert response.headers["content-type"] == XLSX_MEDIA_TYPE
    assert response.headers["content-disposition"] == (
        f'attachment; filename="agrologistix-run-{run_id}.xlsx"'
    )
    return response.content


def test_export_contains_summary_and_one_sheet_per_route(client: TestClient) -> None:
    baseline = _baseline(client)
    payload = _export(client, baseline["run_id"])

    workbook = load_workbook(BytesIO(payload))
    routes = baseline["routes"]

    assert workbook.sheetnames[0] == SUMMARY_TITLE
    assert len(workbook.sheetnames) == len(routes) + 1
    assert all(name.startswith("Рейс ") for name in workbook.sheetnames[1:])

    summary = workbook[SUMMARY_TITLE]
    assert f"№{baseline['run_id']}" in str(summary["A1"].value)
    values = [cell.value for row in summary.iter_rows() for cell in row]
    assert any(
        isinstance(value, float)
        and value == pytest.approx(baseline["metrics"]["total_tco_rub"], abs=0.01)
        for value in values
    )


def test_export_route_sheet_matches_planned_stops(client: TestClient) -> None:
    baseline = _baseline(client)
    workbook = load_workbook(BytesIO(_export(client, baseline["run_id"])))

    first_route = baseline["routes"][0]
    sheet = workbook[workbook.sheetnames[1]]
    header_row = next(row[0].row for row in sheet.iter_rows() if row[0].value == "№")
    headers = [cell.value for cell in sheet[header_row]]
    assert headers[:5] == ["№", "Заказ", "Покупатель", "Урожай", "Отгружено, кг"]
    assert headers[-1] == "Статус"

    rows = [
        [cell.value for cell in row]
        for row in sheet.iter_rows(min_row=header_row + 1)
        if isinstance(row[0].value, int)
    ]
    assert len(rows) == len(first_route["stops"])
    assert [row[0] for row in rows] == [stop["sequence_order"] for stop in first_route["stops"]]
    assert sum(row[4] for row in rows) == pytest.approx(
        sum(stop["shipped_kg"] for stop in first_route["stops"]), abs=0.01
    )
    etas = [row[6] for row in rows]
    assert etas == sorted(etas)


def test_export_of_run_without_routes_still_returns_workbook(client: TestClient) -> None:
    with _database_session(client) as session:
        for truck in session.exec(select(Truck)).all():
            truck.status = "broken"
            session.add(truck)
        session.commit()

    baseline = _baseline(client)
    assert baseline["routes"] == []

    workbook = load_workbook(BytesIO(_export(client, baseline["run_id"])))

    assert workbook.sheetnames == [SUMMARY_TITLE]
    assert baseline["metrics"]["unmet_kg"] > 0


def test_workbook_can_be_built_without_database_entities() -> None:
    run = SimulationRun(
        id=42,
        created_at=datetime(2026, 1, 1, 12, 0, tzinfo=UTC),
        weather_mode="normal",
        total_shipped_kg=150.0,
        total_unmet_kg=0.0,
    )
    stop = ExportStop(
        sequence_order=1,
        order_id=None,
        client_name="—",
        product_name="—",
        warehouse_name="—",
        shipped_kg=150.0,
        leg_distance_km=12.5,
        eta_minutes=20.0,
        freshness_pct=88.0,
        leg_cost_rub=450.0,
        stop_status="planned",
    )
    route = ExportRoute(
        truck_id=7,
        truck_name="Машина 7",
        plate_number="—",
        warehouse_name="—",
        capacity_kg=0.0,
        stops=(stop,),
    )

    workbook = build_workbook(ExportRun(run=run, routes=(route,)))

    assert workbook.sheetnames[0] == SUMMARY_TITLE
    assert "Рейс 1" in workbook.sheetnames[1]
    route_sheet = workbook[workbook.sheetnames[1]]
    header = next(row for row in route_sheet.iter_rows() if row[0].value == "№")
    assert [cell.value for cell in header][:2] == ["№", "Заказ"]
    row = next(row for row in route_sheet.iter_rows() if row[0].value == 1)
    assert row[1].value == "—"
    totals = next(row for row in route_sheet.iter_rows() if row[0].value == "Итого")
    assert totals[4].value == pytest.approx(150.0)
    assert totals[8].value == pytest.approx(450.0)


def test_workbook_of_a_run_without_routes_has_only_the_summary() -> None:
    run = SimulationRun(id=1, created_at=datetime(2026, 1, 1, tzinfo=UTC))

    workbook = build_workbook(ExportRun(run=run, routes=()))

    assert workbook.sheetnames == [SUMMARY_TITLE]


def test_export_rejects_unknown_run_and_missing_pin(client: TestClient) -> None:
    unauthorized = client.get(EXPORT_URL.format(run_id=1))
    missing = client.get(EXPORT_URL.format(run_id=9999), headers=AUTH)

    assert unauthorized.status_code == 401
    assert unauthorized.json()["code"] == "unauthorized"
    assert missing.status_code == 404
    assert missing.json() == {
        "code": "not_found",
        "detail": "Расчёт №9999 не найден",
    }


def test_export_writes_client_names_and_totals(client: TestClient) -> None:
    baseline = _baseline(client)
    workbook = load_workbook(BytesIO(_export(client, baseline["run_id"])))

    sheet = workbook[workbook.sheetnames[1]]
    planned = baseline["routes"][0]
    text_values = {str(cell.value) for row in sheet.iter_rows() for cell in row}
    assert any(value.startswith("Рейс 1") for value in text_values)

    total_row = next(row for row in sheet.iter_rows() if row[0].value == "Итого")
    assert total_row[4].value == pytest.approx(
        sum(stop["shipped_kg"] for stop in planned["stops"]), abs=0.01
    )
    assert total_row[8].value == pytest.approx(
        sum(stop["trip_leg_cost_rub"] for stop in planned["stops"]), abs=0.01
    )

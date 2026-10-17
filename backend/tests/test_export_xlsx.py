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
ROUTES_TITLE = "Рейсы"
ANALYSIS_TITLE = "Аналитика"
NOTES_TITLE = "Замечания"


def _route_sheet_names(workbook) -> list[str]:
    return [name for name in workbook.sheetnames if name.startswith("Рейс ")]


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
    assert workbook.sheetnames[1:4] == [ROUTES_TITLE, ANALYSIS_TITLE, NOTES_TITLE]
    assert len(_route_sheet_names(workbook)) == len(routes)
    assert len(workbook.sheetnames) == len(routes) + 4
    # На сводке — диаграмма «стоимость доставки и потери урожая».
    assert len(workbook[SUMMARY_TITLE]._charts) == 1

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
    sheet = workbook[_route_sheet_names(workbook)[0]]
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

    assert workbook.sheetnames == [SUMMARY_TITLE, ROUTES_TITLE, ANALYSIS_TITLE, NOTES_TITLE]
    assert _route_sheet_names(workbook) == []
    assert baseline["metrics"]["unmet_kg"] > 0


def test_summary_exposes_loss_and_unmet_shares(client: TestClient) -> None:
    baseline = _baseline(client)
    workbook = load_workbook(BytesIO(_export(client, baseline["run_id"])))
    summary = workbook[SUMMARY_TITLE]

    values = {row[0].value: row[1].value for row in summary.iter_rows() if row[0].value is not None}
    metrics = baseline["metrics"]
    assert values["Потери урожая, %"] == pytest.approx(
        100.0 - metrics["avg_freshness_pct"], abs=0.05
    )
    assert values["Не привезли, %"] == pytest.approx(
        metrics["unmet_kg"] / (metrics["shipped_kg"] + metrics["unmet_kg"]) * 100.0,
        abs=0.05,
    )


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
    route_sheet = workbook[_route_sheet_names(workbook)[0]]
    header = next(row for row in route_sheet.iter_rows() if row[0].value == "№")
    assert [cell.value for cell in header][:2] == ["№", "Заказ"]
    row = next(row for row in route_sheet.iter_rows() if row[0].value == 1)
    assert row[1].value == "—"
    totals = next(row for row in route_sheet.iter_rows() if row[0].value == "Итого")
    assert totals[4].value == pytest.approx(150.0)
    assert totals[8].value == pytest.approx(450.0)


def test_workbook_of_a_run_without_routes_has_no_route_sheets() -> None:
    run = SimulationRun(id=1, created_at=datetime(2026, 1, 1, tzinfo=UTC))

    workbook = build_workbook(ExportRun(run=run, routes=()))

    assert workbook.sheetnames == [SUMMARY_TITLE, ROUTES_TITLE, ANALYSIS_TITLE, NOTES_TITLE]


def test_analysis_sheet_totals_match_the_plan(client: TestClient) -> None:
    baseline = _baseline(client)
    workbook = load_workbook(BytesIO(_export(client, baseline["run_id"])))
    sheet = workbook[ANALYSIS_TITLE]

    total_row = next(row for row in sheet.iter_rows() if row[0].value == "Итого")
    metrics = baseline["metrics"]
    ordered_kg = metrics["shipped_kg"] + metrics["unmet_kg"]
    assert total_row[10].value == pytest.approx(metrics["shipped_kg"], abs=0.05)
    assert total_row[12].value == pytest.approx(
        metrics["expected_net_profit_rub"] + metrics["total_tco_rub"], abs=0.05
    )
    # Потери в кг не превышают отгруженный объём и положительны на seed-данных.
    assert 0.0 < total_row[17].value <= ordered_kg
    # Потери — сумма по стопам, округлённая до копеек на каждом стопе.
    assert total_row[18].value == pytest.approx(metrics["total_spoilage_loss_rub"], abs=1.0)
    assert total_row[19].value == pytest.approx(metrics["total_trip_cost_rub"], abs=0.05)
    assert total_row[20].value == pytest.approx(metrics["expected_net_profit_rub"], abs=0.05)


def test_routes_sheet_reports_equipment_and_load(client: TestClient) -> None:
    baseline = _baseline(client)
    workbook = load_workbook(BytesIO(_export(client, baseline["run_id"])))
    sheet = workbook[ROUTES_TITLE]

    text_values = {str(cell.value) for row in sheet.iter_rows() for cell in row}
    assert any("рефрижератор" in value or "без охлаждения" in value for value in text_values)
    header_row = next(row[0].row for row in sheet.iter_rows() if row[0].value == "Рейс")
    first_data_row = header_row + 1
    assert sheet.cell(row=first_data_row, column=6).value > 0.0
    assert 0.0 < sheet.cell(row=first_data_row, column=8).value <= 100.0


def test_notes_sheet_flags_unmet_demand(client: TestClient) -> None:
    with _database_session(client) as session:
        for truck in session.exec(select(Truck)).all():
            truck.status = "broken"
            session.add(truck)
        session.commit()

    baseline = _baseline(client)
    assert baseline["metrics"]["unmet_kg"] > 0

    workbook = load_workbook(BytesIO(_export(client, baseline["run_id"])))
    notes = workbook[NOTES_TITLE]
    messages = [row[2].value for row in notes.iter_rows(min_row=4) if isinstance(row[2].value, str)]
    assert any("Не привезли" in message for message in messages)


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

    sheet = workbook[_route_sheet_names(workbook)[0]]
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

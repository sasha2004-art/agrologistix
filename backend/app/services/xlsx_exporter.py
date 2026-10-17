"""Build an XLSX route sheet for a stored solver run.

The workbook is generated in memory (:class:`io.BytesIO`) with ``openpyxl`` and
contains one summary sheet plus one sheet per route:

* ``Сводка`` — run metadata, weather, metrics and, for ``what_if``, the delta
  against the parent run;
* ``Рейс N`` — truck and warehouse header, the ordered stops with weight, leg
  distance, ETA, expected freshness and leg cost, and the route totals.

Only persisted data is used, so the same exporter serves ``baseline`` and
``what_if`` runs. No PDF engine is involved: printing is a frontend concern.
"""

from dataclasses import dataclass
from io import BytesIO

from openpyxl import Workbook
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter
from openpyxl.worksheet.worksheet import Worksheet
from sqlmodel import Session, select

from app.models.erp_models import Client, Product, Truck, Warehouse
from app.models.run_models import RouteStop, SimulationRun

XLSX_MEDIA_TYPE = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
INVALID_SHEET_CHARS = str.maketrans({char: "-" for char in "[]:*?/\\"})
SHEET_TITLE_LIMIT = 31

HEADER_FILL = PatternFill("solid", fgColor="1F4E78")
HEADER_FONT = Font(bold=True, color="FFFFFF")
TITLE_FONT = Font(bold=True, size=14)
LABEL_FONT = Font(bold=True)
THIN_BORDER = Border(*[Side(style="thin", color="BFBFBF")] * 4)


@dataclass(frozen=True, slots=True)
class ExportStop:
    sequence_order: int
    order_id: int | None
    client_name: str
    product_name: str
    warehouse_name: str
    shipped_kg: float
    leg_distance_km: float
    eta_minutes: float
    freshness_pct: float
    leg_cost_rub: float
    stop_status: str


@dataclass(frozen=True, slots=True)
class ExportRoute:
    truck_id: int
    truck_name: str
    plate_number: str
    warehouse_name: str
    capacity_kg: float
    stops: tuple[ExportStop, ...]

    @property
    def total_kg(self) -> float:
        return round(sum(stop.shipped_kg for stop in self.stops), 3)

    @property
    def total_distance_km(self) -> float:
        return round(sum(stop.leg_distance_km for stop in self.stops), 3)

    @property
    def total_duration_min(self) -> float:
        return round(max((stop.eta_minutes for stop in self.stops), default=0.0), 2)

    @property
    def total_cost_rub(self) -> float:
        return round(sum(stop.leg_cost_rub for stop in self.stops), 2)

    @property
    def final_freshness_pct(self) -> float:
        return round(min((stop.freshness_pct for stop in self.stops), default=100.0), 2)


@dataclass(frozen=True, slots=True)
class ExportRun:
    run: SimulationRun
    routes: tuple[ExportRoute, ...]
    parent: SimulationRun | None = None


def _names(
    session: Session, stop_rows: list[RouteStop]
) -> tuple[dict[int, Truck], dict[int, Warehouse], dict[int, Client], dict[int, Product]]:
    truck_ids = {stop.truck_id for stop in stop_rows}
    warehouse_ids = {stop.warehouse_id for stop in stop_rows}
    client_ids = {stop.client_id for stop in stop_rows}
    product_ids = {stop.product_id for stop in stop_rows}
    trucks = {
        truck.id: truck
        for truck in session.exec(select(Truck).where(Truck.id.in_(truck_ids))).all()
    }
    warehouses = {
        warehouse.id: warehouse
        for warehouse in session.exec(
            select(Warehouse).where(Warehouse.id.in_(warehouse_ids))
        ).all()
    }
    clients = {
        client.id: client
        for client in session.exec(select(Client).where(Client.id.in_(client_ids))).all()
    }
    products = {
        product.id: product
        for product in session.exec(select(Product).where(Product.id.in_(product_ids))).all()
    }
    return trucks, warehouses, clients, products


def load_export_run(session: Session, run_id: int) -> ExportRun | None:
    """Read a stored run with its stops and related names, or ``None``."""

    run = session.get(SimulationRun, run_id)
    if run is None:
        return None

    stop_rows = list(
        session.exec(
            select(RouteStop)
            .where(RouteStop.run_id == run_id)
            .order_by(RouteStop.truck_id, RouteStop.sequence_order)
        ).all()
    )
    trucks, warehouses, clients, products = _names(session, stop_rows)
    parent = session.get(SimulationRun, run.parent_run_id) if run.parent_run_id else None

    grouped: dict[int, list[ExportStop]] = {}
    for stop in stop_rows:
        grouped.setdefault(stop.truck_id, []).append(
            ExportStop(
                sequence_order=stop.sequence_order,
                order_id=stop.order_id,
                client_name=clients[stop.client_id].name if stop.client_id in clients else "-",
                product_name=products[stop.product_id].name if stop.product_id in products else "-",
                warehouse_name=(
                    warehouses[stop.warehouse_id].name if stop.warehouse_id in warehouses else "-"
                ),
                shipped_kg=round(stop.shipped_kg, 3),
                leg_distance_km=round(stop.distance_km, 3),
                eta_minutes=round(stop.eta_minutes, 2),
                freshness_pct=round(stop.expected_freshness * 100.0, 2),
                leg_cost_rub=round(stop.trip_leg_cost_rub, 2),
                stop_status=stop.stop_status,
            )
        )

    routes = tuple(
        ExportRoute(
            truck_id=truck_id,
            truck_name=trucks[truck_id].name if truck_id in trucks else f"Машина {truck_id}",
            plate_number=trucks[truck_id].plate_number if truck_id in trucks else "-",
            warehouse_name=stops[0].warehouse_name,
            capacity_kg=trucks[truck_id].capacity_kg if truck_id in trucks else 0.0,
            stops=tuple(stops),
        )
        for truck_id, stops in grouped.items()
    )
    return ExportRun(run=run, routes=routes, parent=parent)


def _safe_sheet_title(raw: str, used: set[str]) -> str:
    title = raw.translate(INVALID_SHEET_CHARS).strip() or "Лист"
    title = title[:SHEET_TITLE_LIMIT]
    candidate = title
    index = 2
    while candidate.casefold() in used:
        suffix = f" ({index})"
        candidate = f"{title[: SHEET_TITLE_LIMIT - len(suffix)]}{suffix}"
        index += 1
    used.add(candidate.casefold())
    return candidate


def _highlight_header(row: int, width: int, sheet: Worksheet) -> None:
    for column in range(1, width + 1):
        cell = sheet.cell(row=row, column=column)
        cell.fill = HEADER_FILL
        cell.font = HEADER_FONT
        cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
        cell.border = THIN_BORDER


def _autosize(sheet: Worksheet) -> None:
    widths: dict[int, int] = {}
    for row in sheet.iter_rows():
        for cell in row:
            if cell.value is None:
                continue
            widths[cell.column] = max(widths.get(cell.column, 0), len(str(cell.value)))
    for column, width in widths.items():
        sheet.column_dimensions[get_column_letter(column)].width = min(42.0, width + 2.0)


def _write_summary(sheet: Worksheet, report: ExportRun) -> None:
    run = report.run
    metrics = [
        ("TCO, ₽", run.total_tco_rub),
        ("Стоимость рейсов, ₽", run.total_trip_cost_rub),
        ("Потери от порчи, ₽", run.total_spoilage_loss_rub),
        ("Штраф за недовоз, ₽", run.total_unmet_penalty_rub),
        ("Ожидаемая прибыль, ₽", run.expected_net_profit_rub),
        ("Средняя свежесть, %", run.avg_freshness_pct),
        ("Отгружено, кг", run.total_shipped_kg),
        ("Недовоз, кг", run.total_unmet_kg),
    ]

    sheet["A1"] = f"AgroLogistix — маршрутный лист, расчёт №{run.id}"
    sheet["A1"].font = TITLE_FONT
    sheet.merge_cells(start_row=1, start_column=1, end_row=1, end_column=4)

    info = [
        ("Дата расчёта (UTC)", run.created_at.strftime("%d.%m.%Y %H:%M")),
        ("Тип расчёта", "Что, если" if run.parent_run_id else "Базовый"),
        ("Базовый расчёт", f"№{run.parent_run_id}" if run.parent_run_id else "—"),
        ("Погодный режим", run.weather_mode),
        ("Температура, °C", run.temp_c),
        ("Осадки, мм", run.precip_mm),
        ("Рейсов", len(report.routes)),
    ]
    row = 3
    for label, value in info:
        sheet.cell(row=row, column=1, value=label).font = LABEL_FONT
        sheet.cell(row=row, column=2, value=value)
        row += 1

    row += 1
    header_row = row
    headers = ["Показатель", "Значение"]
    if report.parent is not None:
        headers += [f"Было (№{report.parent.id})", "Δ"]
    for column, header in enumerate(headers, start=1):
        sheet.cell(row=header_row, column=column, value=header)
    _highlight_header(header_row, len(headers), sheet)

    row += 1
    for index, (label, value) in enumerate(metrics):
        sheet.cell(row=row, column=1, value=label)
        cell = sheet.cell(row=row, column=2, value=round(value, 2))
        cell.number_format = "#,##0.00"
        if report.parent is not None:
            before = (
                report.parent.total_tco_rub,
                report.parent.total_trip_cost_rub,
                report.parent.total_spoilage_loss_rub,
                report.parent.total_unmet_penalty_rub,
                report.parent.expected_net_profit_rub,
                report.parent.avg_freshness_pct,
                report.parent.total_shipped_kg,
                report.parent.total_unmet_kg,
            )[index]
            sheet.cell(row=row, column=3, value=round(before, 2)).number_format = "#,##0.00"
            delta_cell = sheet.cell(row=row, column=4, value=round(value - before, 2))
            delta_cell.number_format = "#,##0.00;[Red]-#,##0.00"
        row += 1

    row += 1
    sheet.cell(row=row, column=1, value="Рейсы").font = LABEL_FONT
    row += 1
    route_header = row
    for column, header in enumerate(
        [
            "Рейс",
            "Машина",
            "Склад",
            "Стопов",
            "Отгружено, кг",
            "Пробег, км",
            "Время, мин",
            "Стоимость, ₽",
        ],
        start=1,
    ):
        sheet.cell(row=route_header, column=column, value=header)
    _highlight_header(route_header, 8, sheet)
    row += 1
    for index, route in enumerate(report.routes, start=1):
        values = [
            index,
            f"{route.truck_name} ({route.plate_number})",
            route.warehouse_name,
            len(route.stops),
            route.total_kg,
            route.total_distance_km,
            route.total_duration_min,
            route.total_cost_rub,
        ]
        for column, value in enumerate(values, start=1):
            cell = sheet.cell(row=row, column=column, value=value)
            if column in {5, 6, 7, 8}:
                cell.number_format = "#,##0.00"
        row += 1
    _autosize(sheet)


def _write_route(sheet: Worksheet, index: int, route: ExportRoute, run: SimulationRun) -> None:
    sheet["A1"] = f"Рейс {index}: {route.truck_name} ({route.plate_number})"
    sheet["A1"].font = TITLE_FONT
    sheet.merge_cells(start_row=1, start_column=1, end_row=1, end_column=5)

    info = [
        ("Склад загрузки", route.warehouse_name),
        ("Вместимость, кг", route.capacity_kg),
        ("Отгружено, кг", route.total_kg),
        ("Пробег рейса, км", route.total_distance_km),
        ("Время в пути, мин", route.total_duration_min),
        ("Стоимость рейса, ₽", route.total_cost_rub),
        ("Свежесть в последней точке, %", route.final_freshness_pct),
        ("Погодный режим", run.weather_mode),
    ]
    row = 3
    for label, value in info:
        sheet.cell(row=row, column=1, value=label).font = LABEL_FONT
        cell = sheet.cell(row=row, column=2, value=value)
        if isinstance(value, float):
            cell.number_format = "#,##0.00"
        row += 1

    row += 1
    header_row = row
    headers = [
        "№",
        "Заявка",
        "Клиент",
        "Культура",
        "Отгружено, кг",
        "Участок, км",
        "ETA, мин",
        "Свежесть, %",
        "Стоимость участка, ₽",
        "Статус",
    ]
    for column, header in enumerate(headers, start=1):
        sheet.cell(row=header_row, column=column, value=header)
    _highlight_header(header_row, len(headers), sheet)

    row += 1
    for stop in route.stops:
        values = [
            stop.sequence_order,
            stop.order_id if stop.order_id is not None else "—",
            stop.client_name,
            stop.product_name,
            stop.shipped_kg,
            stop.leg_distance_km,
            stop.eta_minutes,
            stop.freshness_pct,
            stop.leg_cost_rub,
            "Доставлено" if stop.stop_status == "delivered" else "Планируется",
        ]
        for column, value in enumerate(values, start=1):
            cell = sheet.cell(row=row, column=column, value=value)
            if column in {5, 6, 7, 8, 9}:
                cell.number_format = "#,##0.00"
            cell.border = THIN_BORDER
        row += 1

    sheet.cell(row=row, column=1, value="Итого").font = LABEL_FONT
    sheet.cell(row=row, column=5, value=route.total_kg).number_format = "#,##0.00"
    sheet.cell(row=row, column=6, value=route.total_distance_km).number_format = "#,##0.00"
    sheet.cell(row=row, column=7, value=route.total_duration_min).number_format = "#,##0.00"
    sheet.cell(row=row, column=8, value=route.final_freshness_pct).number_format = "#,##0.00"
    sheet.cell(row=row, column=9, value=route.total_cost_rub).number_format = "#,##0.00"
    _autosize(sheet)


def build_workbook(report: ExportRun) -> Workbook:
    """Render the report as an ``openpyxl`` workbook."""

    workbook = Workbook()
    summary = workbook.active
    summary.title = "Сводка"
    used_titles = {summary.title.casefold()}
    _write_summary(summary, report)

    for index, route in enumerate(report.routes, start=1):
        title = _safe_sheet_title(f"Рейс {index} {route.plate_number}", used_titles)
        _write_route(workbook.create_sheet(title=title), index, route, report.run)
    return workbook


def export_run_xlsx(report: ExportRun) -> bytes:
    """Serialize the report to XLSX bytes."""

    buffer = BytesIO()
    build_workbook(report).save(buffer)
    return buffer.getvalue()

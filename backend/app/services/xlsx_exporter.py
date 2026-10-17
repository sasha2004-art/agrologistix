"""Build an XLSX route sheet for a stored solver run.

The workbook is generated in memory (:class:`io.BytesIO`) with ``openpyxl``.
Structure:

* ``Сводка`` — run metadata, итоговые метрики и краткая таблица рейсов;
* ``Рейсы`` — подробная аналитика по машинам (оснащение, загрузка, деньги);
* ``Аналитика`` — построчно по остановкам: плечо, ETA, сохранность, выручка,
  потери и маржа;
* ``Замечания`` — пометки, рассчитанные из прогона (недовоз, низкая
  сохранность, недогруженные рейсы, дробление покупателей);
* ``Заказы``, ``Машины``, ``Склады и остатки`` — таблицы сайта на момент
  экспорта (добавляются, когда передан ``session``);
* ``Рейс N <госномер>`` — лист водителя: остановки, итоги, подписи.

Структура книги — обычные таблицы, без диаграмм и символов валюты.
No PDF engine is involved: printing is a frontend concern.
"""

from io import BytesIO

from openpyxl import Workbook
from openpyxl.worksheet.worksheet import Worksheet
from sqlmodel import Session

from app.services.xlsx_analysis import (
    write_analysis_sheet,
    write_notes_sheet,
    write_routes_sheet,
)
from app.services.xlsx_erp import write_orders_sheet, write_stocks_sheet, write_trucks_sheet
from app.services.xlsx_report import (
    LABEL_FONT,
    TITLE_FONT,
    XLSX_MEDIA_TYPE,
    ExportRoute,
    ExportRun,
    ExportStop,
    autosize,
    highlight_header,
    load_export_run,
    safe_sheet_title,
    truck_equipment,
    weather_label,
)

__all__ = [
    "XLSX_MEDIA_TYPE",
    "ExportRoute",
    "ExportRun",
    "ExportStop",
    "build_workbook",
    "export_run_xlsx",
    "load_export_run",
]


def _share_pct(part_kg: float, total_kg: float) -> float:
    """Share of the ordered volume in percent, ``0`` when there was no demand."""

    return round(part_kg / total_kg * 100.0, 2) if total_kg > 0 else 0.0


def _summary_metrics(report: ExportRun) -> list[tuple[str, float]]:
    run = report.run
    ordered_kg = run.total_shipped_kg + run.total_unmet_kg
    # Проценты потерь и недовоза — понятная пользователю замена штрафам.
    spoilage_pct = max(0.0, 100.0 - run.avg_freshness_pct) if run.total_shipped_kg > 0 else 0.0
    return [
        ("Выручка, руб.", report.revenue_rub),
        ("Общие затраты, руб.", run.total_tco_rub),
        ("Затраты на доставку, руб.", run.total_trip_cost_rub),
        ("Потери урожая, руб.", run.total_spoilage_loss_rub),
        ("Потери урожая, кг", report.spoilage_kg),
        ("Потери урожая, %", round(spoilage_pct, 2)),
        ("Прибыль, руб.", run.expected_net_profit_rub),
        ("Сохранность урожая, %", run.avg_freshness_pct),
        ("Привезли, кг", run.total_shipped_kg),
        ("Не привезли, кг", run.total_unmet_kg),
        ("Не привезли, %", _share_pct(run.total_unmet_kg, ordered_kg)),
        ("Рейсов", float(report.trucks_used)),
        ("Загрузка машин, %", report.avg_load_factor_pct),
        ("Покупателей в нескольких рейсах", float(report.split_clients)),
    ]


def _write_summary(sheet: Worksheet, report: ExportRun) -> tuple[int, int, int]:
    """Сводка; возвращает строку шапки, первую строку данных и число рейсов."""

    run = report.run
    metrics = _summary_metrics(report)

    sheet["A1"] = f"AgroLogistix — маршрутный лист, расчёт №{run.id}"
    sheet["A1"].font = TITLE_FONT
    sheet.merge_cells(start_row=1, start_column=1, end_row=1, end_column=4)

    info = [
        ("Дата расчёта", run.created_at.strftime("%d.%m.%Y %H:%M")),
        ("Погода", weather_label(run.weather_mode)),
        ("Температура, °C", run.temp_c),
        ("Осадки, мм", run.precip_mm),
        ("Машин", len(report.routes)),
        ("Выручка, руб.", report.revenue_rub),
        ("Маржа, руб.", round(report.revenue_rub - run.total_tco_rub, 2)),
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
    for column, header in enumerate(["Показатель", "Значение"], start=1):
        sheet.cell(row=header_row, column=column, value=header)
    highlight_header(header_row, 2, sheet)

    row += 1
    for label, value in metrics:
        sheet.cell(row=row, column=1, value=label)
        cell = sheet.cell(row=row, column=2, value=value)
        cell.number_format = "#,##0.00"
        row += 1

    row += 1
    sheet.cell(row=row, column=1, value="Рейсы").font = LABEL_FONT
    row += 1
    route_header = row
    headers = [
        "Рейс",
        "Машина",
        "Склад",
        "Остановок",
        "Отгружено, кг",
        "Пробег, км",
        "Время, мин",
        "Стоимость, руб.",
        "Потери, руб.",
    ]
    for column, header in enumerate(headers, start=1):
        sheet.cell(row=route_header, column=column, value=header)
    highlight_header(route_header, len(headers), sheet)

    row += 1
    first_route_row = row
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
            route.spoilage_rub,
        ]
        for column, value in enumerate(values, start=1):
            cell = sheet.cell(row=row, column=column, value=value)
            if column in {5, 6, 7, 8, 9}:
                cell.number_format = "#,##0.00"
        row += 1

    autosize(sheet)
    return route_header, first_route_row, len(report.routes)


def _write_route(sheet: Worksheet, index: int, route: ExportRoute, run_weather: str) -> None:
    sheet["A1"] = f"Рейс {index}: {route.truck_name} ({route.plate_number})"
    sheet["A1"].font = TITLE_FONT
    sheet.merge_cells(start_row=1, start_column=1, end_row=1, end_column=5)

    info = [
        ("Склад загрузки", route.warehouse_name),
        ("Оснащение", truck_equipment(route)),
        ("Вместимость, кг", route.capacity_kg),
        ("Отгружено, кг", route.total_kg),
        ("Загрузка, %", route.load_factor_pct),
        ("Пробег, км", route.total_distance_km),
        ("Время в пути, мин", route.total_duration_min),
        ("Стоимость, руб.", route.total_cost_rub),
        ("Выручка, руб.", route.revenue_rub),
        ("Потери, руб.", route.spoilage_rub),
        ("Маржа, руб.", route.margin_rub),
        ("Сохранность в последней точке, %", route.final_freshness_pct),
        ("Погода", weather_label(run_weather)),
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
        "Заказ",
        "Покупатель",
        "Урожай",
        "Отгружено, кг",
        "Расстояние, км",
        "В пути, мин",
        "Сохранность, %",
        "Стоимость, руб.",
        "Статус",
    ]
    for column, header in enumerate(headers, start=1):
        sheet.cell(row=header_row, column=column, value=header)
    highlight_header(header_row, len(headers), sheet)

    row += 1
    for stop in route.stops:
        values = [
            stop.sequence_order,
            stop.order_id if stop.order_id is not None else "-",
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
        row += 1

    sheet.cell(row=row, column=1, value="Итого").font = LABEL_FONT
    sheet.cell(row=row, column=5, value=route.total_kg).number_format = "#,##0.00"
    sheet.cell(row=row, column=6, value=route.total_distance_km).number_format = "#,##0.00"
    sheet.cell(row=row, column=7, value=route.total_duration_min).number_format = "#,##0.00"
    sheet.cell(row=row, column=8, value=route.final_freshness_pct).number_format = "#,##0.00"
    sheet.cell(row=row, column=9, value=route.total_cost_rub).number_format = "#,##0.00"
    autosize(sheet)


def build_workbook(report: ExportRun, session: Session | None = None) -> Workbook:
    """Render the report as an ``openpyxl`` workbook.

    С ``session`` добавляются листы текущего ERP (заказы, машины, склады и
    остатки) — те же таблицы, что видит логист на сайте.
    """

    workbook = Workbook()
    summary = workbook.active
    summary.title = "Сводка"
    used_titles = {summary.title.casefold()}
    _write_summary(summary, report)

    for title, writer in (
        ("Рейсы", lambda sheet: write_routes_sheet(sheet, report)),
        ("Аналитика", lambda sheet: write_analysis_sheet(sheet, report)),
        ("Замечания", lambda sheet: write_notes_sheet(sheet, report)),
    ):
        writer(workbook.create_sheet(title=safe_sheet_title(title, used_titles)))

    if session is not None:
        for title, writer in (
            ("Заказы", lambda sheet: write_orders_sheet(sheet, session)),
            ("Машины", lambda sheet: write_trucks_sheet(sheet, session)),
            ("Склады и остатки", lambda sheet: write_stocks_sheet(sheet, session)),
        ):
            writer(workbook.create_sheet(title=safe_sheet_title(title, used_titles)))

    for index, route in enumerate(report.routes, start=1):
        title = safe_sheet_title(f"Рейс {index} {route.plate_number}", used_titles)
        _write_route(workbook.create_sheet(title=title), index, route, report.run.weather_mode)
    return workbook


def export_run_xlsx(report: ExportRun, session: Session | None = None) -> bytes:
    """Serialize the report to XLSX bytes."""

    buffer = BytesIO()
    build_workbook(report, session).save(buffer)
    return buffer.getvalue()

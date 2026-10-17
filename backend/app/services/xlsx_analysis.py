"""Аналитические листы маршрутного листа XLSX.

* «Рейсы» — сводка по машинам: оснащение, загрузка, выручка, потери, маржа;
* «Аналитика» — построчная таблица по остановкам с деньгами и килограммами;
* «Замечания» — пометки, рассчитанные из сохранённого прогона (недовоз,
  низкая сохранность, недогруженные рейсы, дробление покупателей).

Штрафов за недовоз здесь нет: недовоз измеряется килограммами и процентом.
"""

from openpyxl.worksheet.worksheet import Worksheet

from app.services.xlsx_report import (
    ERROR_FILL,
    LABEL_FONT,
    WARNING_FILL,
    ExportRun,
    autosize,
    highlight_header,
    road_label,
    truck_equipment,
)

# Порог свежести из SOLVER_MIN_STOP_FRESHNESS: ниже — пометка о риске.
FRESHNESS_WARNING_PCT = 90.0
FRESHNESS_ERROR_PCT = 80.0
MIN_FRESHNESS_PCT = 70.0
LOW_LOAD_FACTOR_PCT = 50.0

ROUTES_HEADERS = (
    "Рейс",
    "Машина",
    "Госномер",
    "Склад",
    "Оснащение",
    "Вместимость, кг",
    "Отгружено, кг",
    "Загрузка, %",
    "Остановок",
    "Пробег, км",
    "Время, мин",
    "Выручка, руб.",
    "Потери, кг",
    "Потери, руб.",
    "Стоимость, руб.",
    "Маржа, руб.",
    "Сохранность в точках, %",
)

ANALYSIS_HEADERS = (
    "Рейс",
    "Машина",
    "№",
    "Заказ",
    "Покупатель",
    "Адрес",
    "Дорога",
    "Культура",
    "Склад",
    "Партия, %",
    "Отгружено, кг",
    "Цена, руб./кг",
    "Выручка, руб.",
    "Плечо, км",
    "Время плеча, мин",
    "ETA, мин",
    "Сохранность, %",
    "Потери, кг",
    "Потери, руб.",
    "Стоимость плеча, руб.",
    "Маржа, руб.",
    "Этап",
)

NOTES_HEADERS = ("Уровень", "Где", "Замечание")

_MONEY_COLUMNS = {7, 12, 13, 14, 15, 16, 17}


def _write_cell(sheet: Worksheet, row: int, column: int, value: object, *, money: bool = False):
    cell = sheet.cell(row=row, column=column, value=value)
    if money:
        cell.number_format = "#,##0.00"
    return cell


def write_routes_sheet(sheet: Worksheet, report: ExportRun) -> tuple[int, int]:
    """Лист «Рейсы»; возвращает номер шапки и число строк таблицы."""

    sheet["A1"] = f"Аналитика по рейсам, расчёт №{report.run.id}"
    sheet["A1"].font = LABEL_FONT

    header_row = 3
    for column, header in enumerate(ROUTES_HEADERS, start=1):
        sheet.cell(row=header_row, column=column, value=header)
    highlight_header(header_row, len(ROUTES_HEADERS), sheet)

    row = header_row + 1
    for index, route in enumerate(report.routes, start=1):
        values = (
            index,
            route.truck_name,
            route.plate_number,
            route.warehouse_name,
            truck_equipment(route),
            route.capacity_kg,
            route.total_kg,
            route.load_factor_pct,
            len(route.stops),
            route.total_distance_km,
            route.total_duration_min,
            route.revenue_rub,
            route.spoilage_kg,
            route.spoilage_rub,
            route.total_cost_rub,
            route.margin_rub,
            route.final_freshness_pct,
        )
        for column, value in enumerate(values, start=1):
            _write_cell(sheet, row, column, value, money=column in _MONEY_COLUMNS)
        row += 1

    total_row = row
    sheet.cell(row=total_row, column=1, value="Итого").font = LABEL_FONT
    totals = {
        6: sum(route.capacity_kg for route in report.routes),
        7: sum(route.total_kg for route in report.routes),
        10: sum(route.total_distance_km for route in report.routes),
        12: report.revenue_rub,
        13: report.spoilage_kg,
        14: sum(route.spoilage_rub for route in report.routes),
        15: sum(route.total_cost_rub for route in report.routes),
        16: sum(route.margin_rub for route in report.routes),
    }
    for column, value in totals.items():
        _write_cell(sheet, total_row, column, round(value, 2), money=True)

    sheet.auto_filter.ref = f"A{header_row}:{_column_letter(len(ROUTES_HEADERS))}{total_row - 1}"
    sheet.freeze_panes = f"A{header_row + 1}"
    autosize(sheet)
    return header_row, len(report.routes)


def write_analysis_sheet(sheet: Worksheet, report: ExportRun) -> None:
    """Лист «Аналитика»: каждая остановка с выручкой, потерями и маржой."""

    sheet["A1"] = f"Аналитика по остановкам, расчёт №{report.run.id}"
    sheet["A1"].font = LABEL_FONT

    header_row = 3
    for column, header in enumerate(ANALYSIS_HEADERS, start=1):
        sheet.cell(row=header_row, column=column, value=header)
    highlight_header(header_row, len(ANALYSIS_HEADERS), sheet)

    row = header_row + 1
    sums = {11: 0.0, 13: 0.0, 18: 0.0, 19: 0.0, 20: 0.0, 21: 0.0}
    for index, route in enumerate(report.routes, start=1):
        for stop in route.stops:
            values = (
                index,
                route.truck_name,
                stop.sequence_order,
                stop.order_id if stop.order_id is not None else "-",
                stop.client_name,
                stop.client_address,
                road_label(stop.road_type),
                stop.product_name,
                stop.warehouse_name,
                stop.stock_freshness_pct,
                stop.shipped_kg,
                stop.price_per_kg,
                stop.revenue_rub,
                stop.leg_distance_km,
                stop.leg_duration_min,
                stop.eta_minutes,
                stop.freshness_pct,
                stop.spoilage_kg,
                stop.spoilage_rub,
                stop.leg_cost_rub,
                stop.margin_rub,
                "Доставлено" if stop.stop_status == "delivered" else "Планируется",
            )
            for column, value in enumerate(values, start=1):
                cell = _write_cell(sheet, row, column, value, money=column in _MONEY_COLUMNS)
                if column == 17:
                    if stop.freshness_pct < FRESHNESS_ERROR_PCT:
                        cell.fill = ERROR_FILL
                    elif stop.freshness_pct < FRESHNESS_WARNING_PCT:
                        cell.fill = WARNING_FILL
                if column == 21 and stop.margin_rub < 0.0:
                    cell.fill = ERROR_FILL
                if column in sums:
                    sums[column] += float(value)
            row += 1

    total_row = row
    sheet.cell(row=total_row, column=1, value="Итого").font = LABEL_FONT
    for column, value in sums.items():
        _write_cell(sheet, total_row, column, round(value, 2), money=True)

    sheet.auto_filter.ref = f"A{header_row}:{_column_letter(len(ANALYSIS_HEADERS))}{total_row - 1}"
    sheet.freeze_panes = f"A{header_row + 1}"
    autosize(sheet)


def write_notes_sheet(sheet: Worksheet, report: ExportRun) -> None:
    """Лист «Замечания»: аналитические пометки, рассчитанные из прогона."""

    sheet["A1"] = f"Замечания по расчёту №{report.run.id}"
    sheet["A1"].font = LABEL_FONT

    header_row = 3
    for column, header in enumerate(NOTES_HEADERS, start=1):
        sheet.cell(row=header_row, column=column, value=header)
    highlight_header(header_row, len(NOTES_HEADERS), sheet)

    notes = _collect_notes(report)
    row = header_row + 1
    for level, where, text in notes:
        sheet.cell(row=row, column=1, value=level).fill = (
            ERROR_FILL if level == "Ошибка" else WARNING_FILL
        )
        sheet.cell(row=row, column=2, value=where)
        sheet.cell(row=row, column=3, value=text)
        row += 1

    autosize(sheet)


def _collect_notes(report: ExportRun) -> list[tuple[str, str, str]]:
    run = report.run
    ordered_kg = run.total_shipped_kg + run.total_unmet_kg
    notes: list[tuple[str, str, str]] = []

    if run.total_unmet_kg > 0.0:
        share = run.total_unmet_kg / ordered_kg * 100.0 if ordered_kg > 0 else 100.0
        level = "Ошибка" if share >= 50.0 else "Внимание"
        notes.append(
            (
                level,
                "Прогон",
                f"Не привезли {run.total_unmet_kg:.0f} кг ({share:.1f} % от заказанного объёма)",
            )
        )

    for index, route in enumerate(report.routes, start=1):
        for stop in route.stops:
            if stop.freshness_pct < MIN_FRESHNESS_PCT:
                notes.append(
                    (
                        "Внимание",
                        f"Рейс {index}, остановка {stop.sequence_order}",
                        f"{stop.client_name}: сохранность {stop.freshness_pct:.1f} % "
                        f"ниже порога {MIN_FRESHNESS_PCT:.0f} %",
                    )
                )
        if route.load_factor_pct < LOW_LOAD_FACTOR_PCT:
            notes.append(
                (
                    "Внимание",
                    f"Рейс {index}",
                    f"Загрузка {route.load_factor_pct:.1f} % — машина уходит недогруженной",
                )
            )

    if report.split_clients > 0:
        notes.append(
            (
                "Внимание",
                "Покупатели",
                f"Покупателей развезено несколькими машинами: {report.split_clients}",
            )
        )

    if not notes:
        notes.append(
            (
                "Норма",
                "Прогон",
                "Замечаний нет: груз доставлен полностью, сохранность в норме",
            )
        )
    return notes


def _column_letter(column: int) -> str:
    letters = ""
    while column > 0:
        column, remainder = divmod(column - 1, 26)
        letters = chr(65 + remainder) + letters
    return letters

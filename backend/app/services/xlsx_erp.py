"""Листы XLSX с текущим состоянием ERP: заказы, машины, склады и остатки.

Эти листы повторяют таблицы сайта и читаются из БД **на момент экспорта**,
поэтому, в отличие от листов сохранённого прогона, зависят от актуального
состояния ERP. Рендеринг отделён от `xlsx_exporter.py`, чтобы файлы держались
в лимите 500 строк.
"""

from openpyxl.worksheet.worksheet import Worksheet
from sqlmodel import Session, select

from app.models.erp_models import Client, ClientOrder, Product, Truck, Warehouse, WarehouseStock
from app.services.xlsx_report import LABEL_FONT, autosize, highlight_header

ORDER_STATUS_LABELS = {
    "pending": "В плане",
    "in_progress": "В работе",
    "delivered": "Доставлено",
}
TRUCK_STATUS_LABELS = {"active": "В строю", "broken": "Не в работе"}
ROAD_LABELS = {"asphalt": "Асфальт", "dirt": "Грунтовка"}


def _title(sheet: Worksheet, text: str, width: int) -> int:
    """Заголовок листа; возвращает строку шапки таблицы."""

    sheet["A1"] = text
    sheet["A1"].font = LABEL_FONT
    sheet.merge_cells(start_row=1, start_column=1, end_row=1, end_column=width)
    return 3


def _header(sheet: Worksheet, row: int, headers: list[str]) -> int:
    for column, header in enumerate(headers, start=1):
        sheet.cell(row=row, column=column, value=header)
    highlight_header(row, len(headers), sheet)
    return row + 1


def _equipment(truck: Truck) -> str:
    features = ["рефрижератор" if truck.has_reefer else "без охлаждения"]
    if truck.has_insulation:
        features.append("утепление")
    features.append("грунтовка" if truck.can_use_dirt else "только асфальт")
    return ", ".join(features)


def write_orders_sheet(sheet: Worksheet, session: Session, *, account_id: int) -> None:
    """Лист «Заказы»: то же, что таблица заказов на сайте."""

    headers = [
        "№",
        "Покупатель",
        "Адрес",
        "Культура",
        "Заказано, кг",
        "Доставлено, кг",
        "Остаток, кг",
        "Цена, руб./кг",
        "Дорога",
        "Этап",
    ]
    row = _header(sheet, _title(sheet, "Заказы покупателей", len(headers)), headers)

    clients = {
        client.id: client
        for client in session.exec(select(Client).where(Client.account_id == account_id)).all()
    }
    products = {
        product.id: product
        for product in session.exec(select(Product).where(Product.account_id == account_id)).all()
    }
    orders = session.exec(
        select(ClientOrder).where(ClientOrder.account_id == account_id).order_by(ClientOrder.id)
    ).all()

    for order in orders:
        client = clients.get(order.client_id)
        product = products.get(order.product_id)
        remaining = max(0.0, order.requested_kg - order.delivered_kg)
        values = [
            order.id,
            client.name if client else "-",
            client.address if client else "",
            product.name if product else "-",
            order.requested_kg,
            order.delivered_kg,
            remaining,
            order.purchase_price_rub,
            ROAD_LABELS.get(client.road_type if client else "asphalt", "Асфальт"),
            ORDER_STATUS_LABELS.get(order.delivery_status, order.delivery_status),
        ]
        for column, value in enumerate(values, start=1):
            cell = sheet.cell(row=row, column=column, value=value)
            if column in {5, 6, 7, 8}:
                cell.number_format = "#,##0.00"
        row += 1
    autosize(sheet)


def write_trucks_sheet(sheet: Worksheet, session: Session, *, account_id: int) -> None:
    """Лист «Машины»: автопарк как на вкладке «Машины и склады»."""

    headers = [
        "Машина",
        "Госномер",
        "База",
        "Вместимость, кг",
        "Цена за км, руб.",
        "Выезд, руб.",
        "Оснащение",
        "Статус",
    ]
    row = _header(sheet, _title(sheet, "Машины", len(headers)), headers)

    warehouses = {
        warehouse.id: warehouse
        for warehouse in session.exec(select(Warehouse).where(Warehouse.account_id == account_id)).all()
    }
    for truck in session.exec(
        select(Truck).where(Truck.account_id == account_id).order_by(Truck.id)
    ).all():
        base = warehouses.get(truck.warehouse_id)
        values = [
            truck.name,
            truck.plate_number,
            base.name if base else "-",
            truck.capacity_kg,
            truck.cost_per_km_rub,
            truck.fixed_trip_cost_rub,
            _equipment(truck),
            TRUCK_STATUS_LABELS.get(truck.status, truck.status),
        ]
        for column, value in enumerate(values, start=1):
            cell = sheet.cell(row=row, column=column, value=value)
            if column in {4, 5, 6}:
                cell.number_format = "#,##0.00"
        row += 1
    autosize(sheet)


def write_stocks_sheet(sheet: Worksheet, session: Session, *, account_id: int) -> None:
    """Лист «Склады и остатки»: матрица склад × культура с итогами."""

    products = session.exec(
        select(Product).where(Product.account_id == account_id).order_by(Product.id)
    ).all()
    warehouses = session.exec(
        select(Warehouse).where(Warehouse.account_id == account_id).order_by(Warehouse.id)
    ).all()
    stocks = session.exec(select(WarehouseStock).where(WarehouseStock.account_id == account_id)).all()
    available = {(stock.warehouse_id, stock.product_id): stock.available_kg for stock in stocks}

    headers = ["Склад", "Адрес", *[f"{product.name}, кг" for product in products], "Итого, кг"]
    row = _header(sheet, _title(sheet, "Склады и остатки", len(headers)), headers)

    for warehouse in warehouses:
        values: list[object] = [warehouse.name, warehouse.address]
        total = 0.0
        for product in products:
            weight = available.get((warehouse.id, product.id), 0.0)
            total += weight
            values.append(weight)
        values.append(total)
        for column, value in enumerate(values, start=1):
            cell = sheet.cell(row=row, column=column, value=value)
            if column >= 3:
                cell.number_format = "#,##0.00"
        row += 1

    totals: list[object] = ["Итого", ""]
    for product in products:
        totals.append(
            sum(available.get((warehouse.id, product.id), 0.0) for warehouse in warehouses)
        )
    totals.append(sum(value for value in available.values() if value > 0.0))
    for column, value in enumerate(totals, start=1):
        cell = sheet.cell(row=row, column=column, value=value)
        cell.font = LABEL_FONT
        if column >= 3:
            cell.number_format = "#,##0.00"
    autosize(sheet)

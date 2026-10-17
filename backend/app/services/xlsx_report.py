"""Данные маршрутного листа XLSX: загрузка прогона и общие структуры.

Модуль отделён от рендеринга (`xlsx_exporter.py`) и аналитики
(`xlsx_analysis.py`), чтобы файлы держались в лимите 500 строк и не зависели
друг от друга циклически. Здесь только чтение БД и производные показатели
стопа/рейса, которые считаются из сохранённого прогона.
"""

from dataclasses import dataclass
from datetime import datetime

from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter
from openpyxl.worksheet.worksheet import Worksheet
from sqlmodel import Session, select

from app.models.erp_models import (
    Client,
    ClientOrder,
    Product,
    Truck,
    Warehouse,
    WarehouseStock,
)
from app.models.run_models import RouteStop, SimulationRun

XLSX_MEDIA_TYPE = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
INVALID_SHEET_CHARS = str.maketrans({char: "-" for char in "[]:*?/\\"})
SHEET_TITLE_LIMIT = 31

HEADER_FILL = PatternFill("solid", fgColor="1F4E78")
HEADER_FONT = Font(bold=True, color="FFFFFF")
TITLE_FONT = Font(bold=True, size=14)
LABEL_FONT = Font(bold=True)
THIN_BORDER = Border(*[Side(style="thin", color="BFBFBF")] * 4)
WARNING_FILL = PatternFill("solid", fgColor="FFF2CC")
ERROR_FILL = PatternFill("solid", fgColor="F8D7DA")

# Человекочитаемая подпись погоды для итогового файла.
WEATHER_LABELS = {
    "normal": "фактическая",
    "heatwave_35c": "симуляция: жара +35 °C",
    "heavy_rain": "симуляция: сильный дождь",
}

ROAD_LABELS = {"asphalt": "Асфальт", "dirt": "Грунтовка"}


def weather_label(mode: str) -> str:
    """Plain-language weather caption for the workbook."""

    return WEATHER_LABELS.get(mode, mode)


def road_label(road_type: str) -> str:
    """Plain-language approach road caption."""

    return ROAD_LABELS.get(road_type, road_type)


def truck_equipment(route: "ExportRoute") -> str:
    """Строка оснащения машины: рефрижератор, утепление, грунтовая проходимость."""

    features: list[str] = ["рефрижератор" if route.has_reefer else "без охлаждения"]
    if route.has_insulation:
        features.append("утепление")
    features.append("грунтовка" if route.can_use_dirt else "только асфальт")
    return ", ".join(features)


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
    client_address: str = ""
    road_type: str = "asphalt"
    price_per_kg: float = 0.0
    stock_freshness_pct: float = 100.0
    leg_duration_min: float = 0.0
    # Точная свежесть (0..1): потери считаем по ней, а не по округлённому проценту.
    freshness: float = 1.0

    @property
    def revenue_rub(self) -> float:
        return round(self.shipped_kg * self.price_per_kg, 2)

    @property
    def spoilage_kg(self) -> float:
        return round(self.shipped_kg * (1.0 - self.freshness), 3)

    @property
    def spoilage_rub(self) -> float:
        return round(self.shipped_kg * (1.0 - self.freshness) * self.price_per_kg, 2)

    @property
    def margin_rub(self) -> float:
        return round(self.revenue_rub - self.leg_cost_rub - self.spoilage_rub, 2)


@dataclass(frozen=True, slots=True)
class ExportRoute:
    truck_id: int
    truck_name: str
    plate_number: str
    warehouse_name: str
    capacity_kg: float
    stops: tuple[ExportStop, ...]
    has_reefer: bool = False
    has_insulation: bool = False
    can_use_dirt: bool = True

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

    @property
    def revenue_rub(self) -> float:
        return round(sum(stop.revenue_rub for stop in self.stops), 2)

    @property
    def spoilage_kg(self) -> float:
        return round(sum(stop.spoilage_kg for stop in self.stops), 3)

    @property
    def spoilage_rub(self) -> float:
        return round(sum(stop.spoilage_rub for stop in self.stops), 2)

    @property
    def margin_rub(self) -> float:
        return round(self.revenue_rub - self.total_cost_rub - self.spoilage_rub, 2)

    @property
    def load_factor_pct(self) -> float:
        if self.capacity_kg <= 0.0:
            return 0.0
        return round(min(100.0, self.total_kg / self.capacity_kg * 100.0), 2)


@dataclass(frozen=True, slots=True)
class ExportRun:
    run: SimulationRun
    routes: tuple[ExportRoute, ...]

    @property
    def run_timestamp(self) -> datetime:
        return self.run.created_at

    @property
    def revenue_rub(self) -> float:
        return round(sum(route.revenue_rub for route in self.routes), 2)

    @property
    def spoilage_kg(self) -> float:
        return round(sum(route.spoilage_kg for route in self.routes), 3)

    @property
    def trucks_used(self) -> int:
        return len(self.routes)

    @property
    def avg_load_factor_pct(self) -> float:
        capacity = sum(route.capacity_kg for route in self.routes)
        if capacity <= 0.0:
            return 0.0
        shipped = sum(route.total_kg for route in self.routes)
        return round(min(100.0, shipped / capacity * 100.0), 2)

    @property
    def split_clients(self) -> int:
        """Сколько покупателей обслуживают более одной машины."""

        trucks_by_client: dict[str, set[int]] = {}
        for route in self.routes:
            for stop in route.stops:
                trucks_by_client.setdefault(stop.client_name, set()).add(route.truck_id)
        return sum(1 for trucks in trucks_by_client.values() if len(trucks) > 1)


def _names(
    session: Session, stop_rows: list[RouteStop]
) -> tuple[
    dict[int, Truck],
    dict[int, Warehouse],
    dict[int, Client],
    dict[int, Product],
    dict[int, ClientOrder],
    dict[tuple[int, int], WarehouseStock],
]:
    truck_ids = {stop.truck_id for stop in stop_rows}
    warehouse_ids = {stop.warehouse_id for stop in stop_rows}
    client_ids = {stop.client_id for stop in stop_rows}
    product_ids = {stop.product_id for stop in stop_rows}
    order_ids = {stop.order_id for stop in stop_rows if stop.order_id is not None}
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
    orders = {
        order.id: order
        for order in session.exec(select(ClientOrder).where(ClientOrder.id.in_(order_ids))).all()
    }
    stock_rows = session.exec(select(WarehouseStock)).all()
    stock_by_key = {
        (stock.warehouse_id, stock.product_id): stock
        for stock in stock_rows
        if stock.warehouse_id in warehouse_ids and stock.product_id in product_ids
    }
    return trucks, warehouses, clients, products, orders, stock_by_key


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
    trucks, warehouses, clients, products, orders, stocks = _names(session, stop_rows)

    grouped: dict[int, list[ExportStop]] = {}
    for stop in stop_rows:
        client = clients.get(stop.client_id)
        order = orders.get(stop.order_id) if stop.order_id is not None else None
        stock = stocks.get((stop.warehouse_id, stop.product_id))
        stops = grouped.setdefault(stop.truck_id, [])
        # Время плеча: ETA накопительный, поэтому берём разницу с предыдущим стопом.
        previous_eta = stops[-1].eta_minutes if stops else 0.0
        eta = round(stop.eta_minutes, 2)
        stops.append(
            ExportStop(
                sequence_order=stop.sequence_order,
                order_id=stop.order_id,
                client_name=client.name if client else "-",
                product_name=products[stop.product_id].name if stop.product_id in products else "-",
                warehouse_name=(
                    warehouses[stop.warehouse_id].name if stop.warehouse_id in warehouses else "-"
                ),
                shipped_kg=round(stop.shipped_kg, 3),
                leg_distance_km=round(stop.distance_km, 3),
                eta_minutes=eta,
                freshness_pct=round(stop.expected_freshness * 100.0, 2),
                leg_cost_rub=round(stop.trip_leg_cost_rub, 2),
                stop_status=stop.stop_status,
                client_address=client.address if client else "",
                road_type=client.road_type if client else "asphalt",
                # Цена из карточки заявки на момент экспорта; в route_stop она не хранится.
                price_per_kg=order.purchase_price_rub if order else 0.0,
                stock_freshness_pct=round(stock.initial_freshness * 100.0, 2) if stock else 100.0,
                leg_duration_min=round(max(0.0, eta - previous_eta), 2),
                freshness=stop.expected_freshness,
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
            has_reefer=bool(trucks[truck_id].has_reefer) if truck_id in trucks else False,
            has_insulation=bool(trucks[truck_id].has_insulation) if truck_id in trucks else False,
            can_use_dirt=bool(trucks[truck_id].can_use_dirt) if truck_id in trucks else True,
        )
        for truck_id, stops in grouped.items()
    )
    return ExportRun(run=run, routes=routes)


def safe_sheet_title(raw: str, used: set[str]) -> str:
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


def highlight_header(row: int, width: int, sheet: Worksheet) -> None:
    for column in range(1, width + 1):
        cell = sheet.cell(row=row, column=column)
        cell.fill = HEADER_FILL
        cell.font = HEADER_FONT
        cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
        cell.border = THIN_BORDER


def autosize(sheet: Worksheet) -> None:
    widths: dict[int, int] = {}
    for row in sheet.iter_rows():
        for cell in row:
            if cell.value is None:
                continue
            widths[cell.column] = max(widths.get(cell.column, 0), len(str(cell.value)))
    for column, width in widths.items():
        sheet.column_dimensions[get_column_letter(column)].width = min(42.0, width + 2.0)

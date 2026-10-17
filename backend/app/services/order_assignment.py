"""Подбор оптимальной машины и маршрута для одной заявки.

Сервис нужен, когда логист берёт заявку «В работе»: перебираются активные
машины, у которых на базовом складе есть сток нужного урожая, для каждой
считается реальное плечо (кэш Mapbox или haversine-fallback), время в пути,
сохранность и стоимость рейса, а побеждает вариант с минимальной суммой
«доставка + потери» — та же математика, что в полном расчёте поставок.
"""

import json
from dataclasses import dataclass, field

from sqlmodel import Session, select

from app.core.config import Settings
from app.models.erp_models import (
    Client,
    ClientOrder,
    Product,
    Truck,
    Warehouse,
    WarehouseStock,
)
from app.models.run_models import FixedAssignment
from app.schemas.enums import DeliveryStatus, RoadType, TruckStatus
from app.services.distance_matrix import Coordinate, get_route_leg
from app.services.freshness_math import (
    CargoProfile,
    freshness_after_hours,
    precipitation_factor,
    spoilage_loss_rub,
    surface_factor,
)
from app.services.weather_service import WeatherSnapshot

_KG_EPSILON = 1e-6


@dataclass(frozen=True, slots=True)
class OrderAssignment:
    """The cheapest truck and route found for one order."""

    order_id: int
    truck_id: int
    truck_name: str
    warehouse_id: int
    warehouse_name: str
    shipped_kg: float
    distance_km: float
    duration_min: float
    trip_cost_rub: float
    spoilage_loss_rub: float
    total_cost_rub: float
    expected_freshness: float
    # Полилиния (lat, lon) для слоя фиксированных маршрутов на карте.
    geometry: tuple[tuple[float, float], ...] = field(default_factory=tuple)


async def assign_order(
    session: Session,
    settings: Settings,
    order: ClientOrder,
    weather: WeatherSnapshot,
) -> OrderAssignment | None:
    """Pick the cheapest feasible truck/warehouse pair for one order.

    ``None`` means there is no active truck that can carry the outstanding cargo
    (no stock of the product on its base, capacity or dirt-approach mismatch).
    """

    client = session.get(Client, order.client_id)
    product = session.get(Product, order.product_id)
    if client is None or product is None:
        return None

    shipped_kg = max(0.0, order.requested_kg - order.delivered_kg)
    if shipped_kg <= _KG_EPSILON:
        return None

    warehouses = {
        int(warehouse.id or 0): warehouse
        for warehouse in session.exec(select(Warehouse).where(Warehouse.is_active.is_(True))).all()
    }
    stocks = session.exec(
        select(WarehouseStock).where(WarehouseStock.product_id == order.product_id)
    ).all()
    stock_by_warehouse = {stock.warehouse_id: stock for stock in stocks if stock.available_kg > 0.0}
    trucks = session.exec(
        select(Truck).where(Truck.status == TruckStatus.ACTIVE.value).order_by(Truck.id)
    ).all()

    # Added to the first stop of the fixed route, so one truck carries one trip.
    # Existing fixations reserve capacity, stops and (for pending orders) stock,
    # otherwise a mass assignment could overload a truck or the warehouse.
    truck_load_kg: dict[int, float] = {}
    truck_stops: dict[int, int] = {}
    reserved_stock: dict[tuple[int, int], float] = {}
    other_orders = {
        int(item.id or 0): item
        for item in session.exec(select(ClientOrder)).all()
        if item.id is not None
    }
    current_order_id = int(order.id or 0)
    for fixed in session.exec(select(FixedAssignment)).all():
        if fixed.order_id == current_order_id:
            continue
        other = other_orders.get(fixed.order_id)
        if other is None or other.delivery_status == DeliveryStatus.DELIVERED.value:
            continue
        truck_load_kg[fixed.truck_id] = truck_load_kg.get(fixed.truck_id, 0.0) + fixed.shipped_kg
        truck_stops[fixed.truck_id] = truck_stops.get(fixed.truck_id, 0) + 1
        # A pending order has not written its stock off yet, so its fixation
        # keeps those kilograms reserved. An in-progress order already consumed
        # them, and counting them again would double the reservation.
        if other.delivery_status == DeliveryStatus.PENDING.value:
            key = (fixed.warehouse_id, fixed.product_id)
            reserved_stock[key] = reserved_stock.get(key, 0.0) + fixed.shipped_kg

    road_type = RoadType(client.road_type)
    surface = surface_factor(road_type)
    rain = precipitation_factor(weather.precipitation_mm)

    best: OrderAssignment | None = None
    for truck in trucks:
        warehouse = warehouses.get(truck.warehouse_id)
        stock = stock_by_warehouse.get(truck.warehouse_id)
        truck_id = int(truck.id or 0)
        if warehouse is None or stock is None:
            continue
        if truck.capacity_kg + _KG_EPSILON < shipped_kg:
            continue
        if truck_load_kg.get(truck_id, 0.0) + shipped_kg > truck.capacity_kg + _KG_EPSILON:
            continue
        if truck_stops.get(truck_id, 0) >= settings.solver_max_stops_per_trip:
            continue
        reserved = reserved_stock.get((truck.warehouse_id, order.product_id), 0.0)
        if stock.available_kg - reserved + _KG_EPSILON < shipped_kg:
            continue
        if road_type is RoadType.DIRT and not truck.can_use_dirt:
            continue

        leg = await get_route_leg(
            session,
            Coordinate(lat=warehouse.lat, lon=warehouse.lon),
            Coordinate(lat=client.lat, lon=client.lon),
            settings,
        )
        travel_hours = leg.distance_km / truck.cruise_speed_kmh * surface * rain
        cargo = CargoProfile(
            spoilage_rate=product.base_spoilage_rate,
            initial_freshness=stock.initial_freshness,
            price_per_kg=order.purchase_price_rub,
        )
        freshness = freshness_after_hours(
            cargo,
            travel_hours,
            weather.temperature_c,
            truck.has_reefer,
            truck.has_insulation,
        )
        trip_cost_rub = truck.fixed_trip_cost_rub + leg.distance_km * truck.cost_per_km_rub
        spoilage_rub = spoilage_loss_rub(shipped_kg, freshness, order.purchase_price_rub)

        candidate = OrderAssignment(
            order_id=int(order.id or 0),
            truck_id=int(truck.id or 0),
            truck_name=truck.name,
            warehouse_id=int(warehouse.id or 0),
            warehouse_name=warehouse.name,
            shipped_kg=round(shipped_kg, 3),
            distance_km=leg.distance_km,
            duration_min=round(travel_hours * 60.0, 2),
            trip_cost_rub=round(trip_cost_rub, 2),
            spoilage_loss_rub=round(spoilage_rub, 2),
            total_cost_rub=round(trip_cost_rub + spoilage_rub, 2),
            expected_freshness=round(freshness, 6),
            geometry=tuple(leg.geometry),
        )
        if best is None or (candidate.total_cost_rub, candidate.truck_id) < (
            best.total_cost_rub,
            best.truck_id,
        ):
            best = candidate

    return best


def save_fixed_assignment(
    session: Session, assignment: OrderAssignment, order: ClientOrder
) -> FixedAssignment:
    """Сохранить (или обновить) фиксацию маршрута для заявки."""

    fixed = session.exec(
        select(FixedAssignment).where(FixedAssignment.order_id == assignment.order_id)
    ).first()
    geometry_json = json.dumps([[lat, lon] for lat, lon in assignment.geometry])
    if fixed is None:
        fixed = FixedAssignment(
            order_id=assignment.order_id,
            truck_id=assignment.truck_id,
            warehouse_id=assignment.warehouse_id,
            client_id=order.client_id,
            product_id=order.product_id,
            shipped_kg=assignment.shipped_kg,
        )
    fixed.truck_id = assignment.truck_id
    fixed.warehouse_id = assignment.warehouse_id
    fixed.client_id = order.client_id
    fixed.product_id = order.product_id
    fixed.shipped_kg = assignment.shipped_kg
    fixed.distance_km = assignment.distance_km
    fixed.duration_min = assignment.duration_min
    fixed.expected_freshness = assignment.expected_freshness
    fixed.trip_cost_rub = assignment.trip_cost_rub
    fixed.geojson_geometry = geometry_json
    session.add(fixed)
    session.commit()
    session.refresh(fixed)
    return fixed


def clear_fixed_assignment(session: Session, order_id: int) -> None:
    """Убрать фиксацию: заявка вернулась «В плане» или закрыта."""

    fixed = session.exec(
        select(FixedAssignment).where(FixedAssignment.order_id == order_id)
    ).first()
    if fixed is not None:
        session.delete(fixed)
        session.commit()


def load_fixed_assignments(session: Session) -> list[FixedAssignment]:
    return list(session.exec(select(FixedAssignment).order_by(FixedAssignment.id)).all())


def assignment_geometry(fixed: FixedAssignment) -> list[tuple[float, float]]:
    """Полилиния фиксации; пустой список при повреждённом JSON."""

    if not fixed.geojson_geometry:
        return []
    try:
        return [(float(lat), float(lon)) for lat, lon in json.loads(fixed.geojson_geometry)]
    except (TypeError, ValueError):
        return []

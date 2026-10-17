"""Подбор оптимальной машины и маршрута для одной заявки.

Сервис нужен, когда логист берёт заявку «В работе»: перебираются активные
машины, у которых на базовом складе есть сток нужного урожая, для каждой
считается реальное плечо (кэш Mapbox или haversine-fallback), время в пути,
сохранность и стоимость рейса, а побеждает вариант с минимальной суммой
«доставка + потери» — та же математика, что в полном расчёте поставок.
"""

from dataclasses import dataclass

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
from app.schemas.enums import RoadType, TruckStatus
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

    road_type = RoadType(client.road_type)
    surface = surface_factor(road_type)
    rain = precipitation_factor(weather.precipitation_mm)

    best: OrderAssignment | None = None
    for truck in trucks:
        warehouse = warehouses.get(truck.warehouse_id)
        stock = stock_by_warehouse.get(truck.warehouse_id)
        if warehouse is None or stock is None:
            continue
        if truck.capacity_kg + _KG_EPSILON < shipped_kg:
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
        )
        if best is None or (candidate.total_cost_rub, candidate.truck_id) < (
            best.total_cost_rub,
            best.truck_id,
        ):
            best = candidate

    return best

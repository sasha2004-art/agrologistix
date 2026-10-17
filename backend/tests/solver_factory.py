"""Shared solver input factory for routing and constraint tests."""

from app.schemas.enums import RoadType, TruckStatus
from app.services.distance_matrix import Coordinate, fallback_leg
from app.services.solver_engine import (
    SolverInput,
    SolverLeg,
    SolverOrder,
    SolverProduct,
    SolverStock,
    SolverTruck,
    SolverWarehouse,
    SolverWeather,
)

OBININSK = (55.0968, 36.6103)
DETCHINO = (54.8083, 36.2333)
KALUGA = (54.5138, 36.2612)
BOROVSK = (55.2075, 36.4850)
BALABANOVO = (55.1797, 36.6597)


def _leg(origin: tuple[float, float], destination: tuple[float, float]) -> SolverLeg:
    fallback = fallback_leg(
        Coordinate(lat=origin[0], lon=origin[1]),
        Coordinate(lat=destination[0], lon=destination[1]),
    )
    return SolverLeg(
        origin=origin,
        destination=destination,
        distance_km=fallback.distance_km,
        base_duration_min=fallback.base_duration_min,
        geometry=tuple(fallback.geometry),
    )


def _point_legs(points: list[tuple[float, float]]) -> tuple:
    return tuple(
        _leg(origin, destination)
        for origin in points
        for destination in points
        if origin != destination
    )


def _warehouse(warehouse_id: int = 1, point: tuple[float, float] = OBININSK) -> SolverWarehouse:
    return SolverWarehouse(
        warehouse_id=warehouse_id,
        name=f"Склад {warehouse_id}",
        latitude=point[0],
        longitude=point[1],
    )


def _order(
    order_id: int = 1,
    *,
    client_id: int = 1,
    product_id: int = 1,
    kg: float = 1000.0,
    price: float = 300.0,
    penalty: float = 100.0,
    road_type: RoadType = RoadType.ASPHALT,
    point: tuple[float, float] = KALUGA,
) -> SolverOrder:
    return SolverOrder(
        order_id=order_id,
        client_id=client_id,
        product_id=product_id,
        requested_kg=kg,
        price_per_kg=price,
        penalty_per_kg=penalty,
        road_type=road_type,
        latitude=point[0],
        longitude=point[1],
    )


def _truck(
    truck_id: int = 1,
    *,
    warehouse_id: int = 1,
    capacity: float = 10_000.0,
    speed: float = 60.0,
    cost_km: float = 30.0,
    fixed: float = 3000.0,
    reefer: bool = True,
    dirt: bool = True,
    status: TruckStatus = TruckStatus.ACTIVE,
) -> SolverTruck:
    return SolverTruck(
        truck_id=truck_id,
        name=f"Машина {truck_id}",
        warehouse_id=warehouse_id,
        capacity_kg=capacity,
        cruise_speed_kmh=speed,
        cost_per_km_rub=cost_km,
        fixed_trip_cost_rub=fixed,
        has_reefer=reefer,
        can_use_dirt=dirt,
        status=status,
    )


def _stock(
    warehouse_id: int = 1,
    product_id: int = 1,
    kg: float = 10_000.0,
    freshness: float = 1.0,
) -> SolverStock:
    return SolverStock(
        warehouse_id=warehouse_id,
        product_id=product_id,
        available_kg=kg,
        initial_freshness=freshness,
    )


def _make_input(
    *,
    orders: list[SolverOrder],
    trucks: list[SolverTruck],
    stocks: list[SolverStock] | None = None,
    warehouses: list[SolverWarehouse] | None = None,
    weather: SolverWeather | None = None,
    frozen: tuple[int, ...] = (),
) -> SolverInput:
    warehouse_list = warehouses or [_warehouse()]
    points = [(warehouse.latitude, warehouse.longitude) for warehouse in warehouse_list] + [
        (order.latitude, order.longitude) for order in orders
    ]
    return SolverInput(
        products=(SolverProduct(product_id=1, spoilage_rate=0.08, base_cost_rub=180.0),),
        stocks=tuple(stocks if stocks is not None else [_stock()]),
        orders=tuple(orders),
        trucks=tuple(trucks),
        legs=_point_legs(points),
        weather=weather or SolverWeather(temperature_c=20.0, precipitation_mm=0.0, mode="normal"),
        warehouses=tuple(warehouse_list),
        frozen_order_ids=frozen,
    )

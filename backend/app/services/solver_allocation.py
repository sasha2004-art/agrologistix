"""Load allocation: MILP distribution of orders over trucks with unmet slack.

The MILP is always feasible: every order keeps a slack variable ``u >= 0`` with a
high ``penalty_per_kg`` price, so a scenario with no trucks still returns a valid
plan where the whole demand is marked unmet.

Decision variables
------------------
* ``x[k, o]`` — kilograms delivered by truck ``k`` for order ``o`` (continuous);
* ``u[o]`` — unmet kilograms of order ``o`` (continuous slack);
* ``y[k]`` — 1 when truck ``k`` is used at all (binary, pays ``fixed_trip_cost``).

Constraints
-----------
* coverage: ``sum_k x[k, o] + u[o] = requested_kg[o]``;
* capacity: ``sum_o x[k, o] <= capacity_kg[k] * y[k]``;
* warehouse stock: ``sum_{o: p} x[k, o] <= stock[base(k), p] * y[k]``;
* dirt: ``x[k, o]`` is fixed to zero when ``truck_can_serve_order`` is false.

Objective: spoilage loss + proportional trip cost + unmet penalties + fixed trip
costs. When HiGHS fails or hits the time limit, a greedy priority fallback is
used so the engine never raises.
"""

import logging
from dataclasses import dataclass

import numpy as np
from scipy.optimize import Bounds, LinearConstraint, milp

from app.schemas.enums import RoadType
from app.services.freshness_math import (
    CargoProfile,
    freshness_after_hours,
    precipitation_factor,
    surface_factor,
)
from app.services.solver_contract import (
    SolverInput,
    SolverOrder,
    SolverProduct,
    SolverStock,
    SolverTruck,
    truck_can_serve_order,
)
from app.services.solver_routing import LegIndex

EPSILON = 1e-6
WEIGHT_PRECISION = 3

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class TruckLoad:
    truck: SolverTruck
    loads: tuple[tuple[SolverOrder, float], ...]


@dataclass(frozen=True, slots=True)
class AllocationResult:
    truck_loads: tuple[TruckLoad, ...]
    unmet: dict[int, float]
    method: str
    unreachable_order_ids: frozenset[int]


def _products_by_id(products: tuple[SolverProduct, ...]) -> dict[int, SolverProduct]:
    return {product.product_id: product for product in products}


def _stocks_by_key(stocks: tuple[SolverStock, ...]) -> dict[tuple[int, int], SolverStock]:
    return {(stock.warehouse_id, stock.product_id): stock for stock in stocks}


def unit_cost_rub(
    solver_input: SolverInput,
    truck: SolverTruck,
    order: SolverOrder,
    index: LegIndex,
    products: dict[int, SolverProduct],
    stocks: dict[tuple[int, int], SolverStock],
    origin: tuple[float, float],
) -> float:
    """Estimated cost of shipping one kilogram of ``order`` with ``truck``."""

    distance_km = index.distance_km(origin, (order.latitude, order.longitude))
    travel_hours = (
        distance_km
        / truck.cruise_speed_kmh
        * surface_factor(order.road_type)
        * precipitation_factor(solver_input.weather.precipitation_mm)
    )
    stock = stocks.get((truck.warehouse_id, order.product_id))
    cargo = CargoProfile(
        spoilage_rate=products[order.product_id].spoilage_rate,
        initial_freshness=stock.initial_freshness if stock else 1.0,
        price_per_kg=order.price_per_kg,
    )
    freshness = freshness_after_hours(
        cargo,
        travel_hours,
        solver_input.weather.temperature_c,
        truck.has_reefer,
    )
    spoilage_per_kg = (1.0 - freshness) * order.price_per_kg
    trip_share = truck.cost_per_km_rub * distance_km / max(order.requested_kg, 1.0)
    return spoilage_per_kg + trip_share


def _milp_allocate(
    solver_input: SolverInput,
    orders: list[SolverOrder],
    trucks: list[SolverTruck],
    products: dict[int, SolverProduct],
    stocks: dict[tuple[int, int], SolverStock],
    origins: dict[int, tuple[float, float]],
    index: LegIndex,
    time_limit_sec: float,
) -> tuple[dict[tuple[int, int], float], dict[int, float]] | None:
    truck_count = len(trucks)
    order_count = len(orders)
    if truck_count == 0:
        return None

    variable_count = truck_count * order_count + order_count + truck_count

    def x_index(truck_position: int, order_position: int) -> int:
        return truck_position * order_count + order_position

    def u_index(order_position: int) -> int:
        return truck_count * order_count + order_position

    def y_index(truck_position: int) -> int:
        return truck_count * order_count + order_count + truck_position

    cost = np.zeros(variable_count)
    lower = np.zeros(variable_count)
    upper = np.zeros(variable_count)
    integrality = np.zeros(variable_count)

    allowed: dict[tuple[int, int], bool] = {}
    for truck_position, truck in enumerate(trucks):
        origin = origins[truck.warehouse_id]
        for order_position, order in enumerate(orders):
            can_serve = truck_can_serve_order(truck, order)
            stock = stocks.get((truck.warehouse_id, order.product_id))
            has_stock = stock is not None and stock.available_kg > EPSILON
            allowed[(truck_position, order_position)] = can_serve and has_stock
            cost[x_index(truck_position, order_position)] = (
                unit_cost_rub(solver_input, truck, order, index, products, stocks, origin)
                if allowed[(truck_position, order_position)]
                else 0.0
            )
            upper[x_index(truck_position, order_position)] = (
                order.requested_kg if allowed[(truck_position, order_position)] else 0.0
            )
        cost[y_index(truck_position)] = truck.fixed_trip_cost_rub
        upper[y_index(truck_position)] = 1.0
        integrality[y_index(truck_position)] = 1

    for order_position, order in enumerate(orders):
        cost[u_index(order_position)] = order.penalty_per_kg
        upper[u_index(order_position)] = order.requested_kg

    rows: list[np.ndarray] = []
    row_lower: list[float] = []
    row_upper: list[float] = []

    for order_position, order in enumerate(orders):
        row = np.zeros(variable_count)
        for truck_position in range(truck_count):
            row[x_index(truck_position, order_position)] = 1.0
        row[u_index(order_position)] = 1.0
        rows.append(row)
        row_lower.append(order.requested_kg)
        row_upper.append(order.requested_kg)

    for truck_position, truck in enumerate(trucks):
        row = np.zeros(variable_count)
        for order_position in range(order_count):
            row[x_index(truck_position, order_position)] = 1.0
        row[y_index(truck_position)] = -truck.capacity_kg
        rows.append(row)
        row_lower.append(-np.inf)
        row_upper.append(0.0)

    product_ids = sorted({order.product_id for order in orders})
    for truck_position, truck in enumerate(trucks):
        for product_id in product_ids:
            stock = stocks.get((truck.warehouse_id, product_id))
            row = np.zeros(variable_count)
            for order_position, order in enumerate(orders):
                if order.product_id == product_id:
                    row[x_index(truck_position, order_position)] = 1.0
            row[y_index(truck_position)] = -(stock.available_kg if stock else 0.0)
            rows.append(row)
            row_lower.append(-np.inf)
            row_upper.append(0.0)

    result = milp(
        c=cost,
        constraints=[LinearConstraint(np.vstack(rows), row_lower, row_upper)],
        integrality=integrality,
        bounds=Bounds(lower, upper),
        options={"time_limit": max(time_limit_sec, 0.01), "presolve": True},
    )
    if result.x is None:
        return None

    allocation: dict[tuple[int, int], float] = {}
    unmet: dict[int, float] = {}
    for truck_position, truck in enumerate(trucks):
        for order_position, order in enumerate(orders):
            kilograms = float(result.x[x_index(truck_position, order_position)])
            if kilograms > EPSILON and allowed[(truck_position, order_position)]:
                allocation[(truck.truck_id, order.order_id)] = kilograms
    for order_position, order in enumerate(orders):
        unmet[order.order_id] = float(result.x[u_index(order_position)])
    return allocation, unmet


def _greedy_allocate(
    orders: list[SolverOrder],
    trucks: list[SolverTruck],
    stocks: dict[tuple[int, int], SolverStock],
    origins: dict[int, tuple[float, float]],
    index: LegIndex,
) -> tuple[dict[tuple[int, int], float], dict[int, float]]:
    capacity_left = {truck.truck_id: truck.capacity_kg for truck in trucks}
    stock_left = {key: stock.available_kg for key, stock in stocks.items()}
    allocation: dict[tuple[int, int], float] = {}
    unmet: dict[int, float] = {}

    priority = sorted(
        orders,
        key=lambda order: order.penalty_per_kg * order.requested_kg,
        reverse=True,
    )
    for order in priority:
        remaining = order.requested_kg
        origin = (order.latitude, order.longitude)
        candidates = [
            truck
            for truck in trucks
            if truck_can_serve_order(truck, order) and capacity_left[truck.truck_id] > EPSILON
        ]
        candidates.sort(key=lambda truck: index.distance_km(origins[truck.warehouse_id], origin))
        for truck in candidates:
            if remaining <= EPSILON:
                break
            available_stock = stock_left.get((truck.warehouse_id, order.product_id), 0.0)
            take = min(remaining, capacity_left[truck.truck_id], available_stock)
            if take <= EPSILON:
                continue
            allocation[(truck.truck_id, order.order_id)] = (
                allocation.get((truck.truck_id, order.order_id), 0.0) + take
            )
            capacity_left[truck.truck_id] -= take
            stock_left[(truck.warehouse_id, order.product_id)] = available_stock - take
            remaining -= take
        unmet[order.order_id] = remaining
    return allocation, unmet


def allocate_loads(
    solver_input: SolverInput,
    orders: list[SolverOrder],
    trucks: list[SolverTruck],
    index: LegIndex,
    time_limit_sec: float,
) -> AllocationResult:
    """Distribute pending orders over active trucks, marking leftovers as unmet."""

    products = _products_by_id(solver_input.products)
    stocks = _stocks_by_key(solver_input.stocks)
    origins = {
        warehouse.warehouse_id: (warehouse.latitude, warehouse.longitude)
        for warehouse in solver_input.warehouses
    }
    usable_trucks = [truck for truck in trucks if truck.warehouse_id in origins]

    unreachable = frozenset(
        order.order_id
        for order in orders
        if order.road_type is RoadType.DIRT
        and not any(truck_can_serve_order(truck, order) for truck in usable_trucks)
    )

    method = "milp"
    milp_result = None
    if usable_trucks:
        try:
            milp_result = _milp_allocate(
                solver_input,
                orders,
                usable_trucks,
                products,
                stocks,
                origins,
                index,
                time_limit_sec,
            )
        except (ValueError, RuntimeError, ArithmeticError) as error:
            # HiGHS may raise on degenerate data; the greedy fallback keeps the
            # endpoint responding with a feasible plan instead of a 500.
            logger.warning("MILP allocation failed, using greedy fallback: %s", error)
            milp_result = None
    if milp_result is None:
        method = "greedy"
        allocation, unmet = _greedy_allocate(orders, usable_trucks, stocks, origins, index)
    else:
        allocation, unmet = milp_result

    orders_by_id = {order.order_id: order for order in orders}
    truck_loads: list[TruckLoad] = []
    for truck in usable_trucks:
        loads = [
            (orders_by_id[order_id], round(kilograms, WEIGHT_PRECISION))
            for (truck_id, order_id), kilograms in allocation.items()
            if truck_id == truck.truck_id and kilograms > EPSILON
        ]
        if loads:
            truck_loads.append(TruckLoad(truck=truck, loads=tuple(loads)))

    return AllocationResult(
        truck_loads=tuple(truck_loads),
        unmet={order_id: round(kg, WEIGHT_PRECISION) for order_id, kg in unmet.items()},
        method=method,
        unreachable_order_ids=unreachable,
    )

"""Bio-logistics solver engine: allocation, routing, metrics and warnings.

``run_solver`` is a pure synchronous function so the whole plan can be computed
outside the event loop; :func:`solve_async` wraps it with ``asyncio.to_thread``
for FastAPI endpoints. The HiGHS time limit is bounded by the caller
(``SOLVER_TIME_LIMIT_SEC``) and the greedy fallback keeps the engine alive even
when the MILP hits that limit.
"""

import asyncio
from time import perf_counter

from app.schemas.enums import TruckStatus, WarningSeverity
from app.services.solver_allocation import AllocationResult, allocate_loads
from app.services.solver_contract import (
    PlannedMetrics,
    PlannedRoute,
    PlannedStop,
    PlannedWarning,
    SolverInput,
    SolverLeg,
    SolverOrder,
    SolverOutcome,
    SolverProduct,
    SolverStock,
    SolverTruck,
    SolverWarehouse,
    SolverWeather,
    truck_can_serve_order,
)
from app.services.solver_routing import LegIndex, LoadedOrder, RouteBuildContext, build_route

__all__ = [
    "PlannedMetrics",
    "PlannedRoute",
    "PlannedStop",
    "PlannedWarning",
    "SolverInput",
    "SolverLeg",
    "SolverOrder",
    "SolverOutcome",
    "SolverProduct",
    "SolverStock",
    "SolverTruck",
    "SolverWarehouse",
    "SolverWeather",
    "run_solver",
    "solve_async",
    "truck_can_serve_order",
]

DEFAULT_SOLVER_TIME_LIMIT_SEC = 1.0
HEAT_THRESHOLD_C = 22.0


def _orders_by_id(orders: list[SolverOrder]) -> dict[int, SolverOrder]:
    return {order.order_id: order for order in orders}


def _collect_metrics(
    routes: list[PlannedRoute],
    allocation: AllocationResult,
    orders: list[SolverOrder],
    capacity_by_truck: dict[int, float],
) -> PlannedMetrics:
    orders_by_id = _orders_by_id(orders)

    trip_cost = sum(route.total_cost_rub for route in routes)
    shipped_kg = 0.0
    revenue_rub = 0.0
    spoilage_loss_rub = 0.0
    weighted_freshness = 0.0
    used_capacity_kg = 0.0
    trucks_used: set[int] = set()
    client_trucks: dict[int, set[int]] = {}
    for route in routes:
        trucks_used.add(route.truck_id)
        used_capacity_kg += capacity_by_truck.get(route.truck_id, 0.0)
        for stop in route.stops:
            order = orders_by_id.get(stop.order_id or -1)
            price = order.price_per_kg if order else 0.0
            shipped_kg += stop.shipped_kg
            revenue_rub += stop.shipped_kg * price
            spoilage_loss_rub += stop.shipped_kg * (1.0 - stop.expected_freshness) * price
            weighted_freshness += stop.shipped_kg * stop.expected_freshness
            client_trucks.setdefault(stop.client_id, set()).add(route.truck_id)

    unmet_kg = sum(allocation.unmet.values())
    unmet_penalty_rub = sum(
        kilograms * orders_by_id[order_id].penalty_per_kg
        for order_id, kilograms in allocation.unmet.items()
        if order_id in orders_by_id
    )
    total_tco_rub = trip_cost + spoilage_loss_rub + unmet_penalty_rub
    avg_freshness_pct = (weighted_freshness / shipped_kg * 100.0) if shipped_kg > 0 else 0.0
    load_factor_pct = (shipped_kg / used_capacity_kg * 100.0) if used_capacity_kg > 0 else 0.0

    return PlannedMetrics(
        total_tco_rub=round(total_tco_rub, 2),
        total_trip_cost_rub=round(trip_cost, 2),
        total_spoilage_loss_rub=round(spoilage_loss_rub, 2),
        total_unmet_penalty_rub=round(unmet_penalty_rub, 2),
        expected_net_profit_rub=round(revenue_rub - total_tco_rub, 2),
        avg_freshness_pct=round(min(100.0, max(0.0, avg_freshness_pct)), 2),
        shipped_kg=round(shipped_kg, 3),
        unmet_kg=round(unmet_kg, 3),
        total_trips=len(trucks_used),
        avg_load_factor_pct=round(min(100.0, max(0.0, load_factor_pct)), 2),
        split_clients=sum(1 for truck_ids in client_trucks.values() if len(truck_ids) > 1),
    )


def _collect_warnings(
    solver_input: SolverInput,
    orders: list[SolverOrder],
    allocation: AllocationResult,
    routes: list[PlannedRoute],
    active_trucks: list[SolverTruck],
    metrics: PlannedMetrics,
) -> list[PlannedWarning]:
    warnings: list[PlannedWarning] = []
    orders_by_id = _orders_by_id(orders)

    broken_count = len(solver_input.trucks) - len(active_trucks)
    if broken_count > 0:
        warnings.append(
            PlannedWarning(
                code="broken_trucks_excluded",
                message=f"Сломанные машины исключены из расчёта: {broken_count}",
                severity=WarningSeverity.INFO.value,
            )
        )

    if not active_trucks and orders:
        warnings.append(
            PlannedWarning(
                code="no_active_trucks",
                message="Нет ни одной машины в строю: весь объём уходит в недовоз",
                severity=WarningSeverity.ERROR.value,
            )
        )

    requested_kg = sum(order.requested_kg for order in orders)
    if metrics.unmet_kg > 0:
        ratio = metrics.unmet_kg / requested_kg if requested_kg > 0 else 1.0
        severity = WarningSeverity.ERROR.value if ratio >= 0.5 else WarningSeverity.WARNING.value
        warnings.append(
            PlannedWarning(
                code="unmet_demand",
                message=(
                    f"Недовоз {metrics.unmet_kg:.0f} кг: не хватает транспорта, "
                    f"остатков или подходящих машин"
                ),
                severity=severity,
            )
        )

    for order_id in sorted(allocation.unreachable_order_ids):
        order = orders_by_id[order_id]
        warnings.append(
            PlannedWarning(
                code="dirt_unreachable",
                message=("Точка недоступна: требуется транспорт с допуском к грунтовым дорогам"),
                severity=WarningSeverity.ERROR.value,
                client_id=order.client_id,
                order_id=order.order_id,
            )
        )

    if solver_input.weather.temperature_c > HEAT_THRESHOLD_C:
        unrefrigerated = {truck.truck_id for truck in active_trucks if not truck.has_reefer}
        heat_risk = [route for route in routes if route.truck_id in unrefrigerated and route.stops]
        if heat_risk:
            warnings.append(
                PlannedWarning(
                    code="heat_without_reefer",
                    message=(
                        f"Жара +{solver_input.weather.temperature_c:.0f} °C: "
                        f"{len(heat_risk)} рейс(а) без рефрижератора, груз портится быстрее"
                    ),
                    severity=WarningSeverity.WARNING.value,
                )
            )

    products = {product.product_id: product for product in solver_input.products}
    stock_by_product: dict[int, float] = {}
    for stock in solver_input.stocks:
        stock_by_product[stock.product_id] = (
            stock_by_product.get(stock.product_id, 0.0) + stock.available_kg
        )
    for product_id, product in products.items():
        requested = sum(order.requested_kg for order in orders if order.product_id == product_id)
        if requested > 0 and stock_by_product.get(product_id, 0.0) < requested:
            warnings.append(
                PlannedWarning(
                    code="stock_shortage",
                    message=(
                        f"Остатков «{product.name or product.product_id}» не хватает: "
                        f"запрошено {requested:.0f} кг, на складах "
                        f"{stock_by_product.get(product_id, 0.0):.0f} кг"
                    ),
                    severity=WarningSeverity.WARNING.value,
                )
            )

    return warnings


def run_solver(
    solver_input: SolverInput,
    time_limit_sec: float = DEFAULT_SOLVER_TIME_LIMIT_SEC,
) -> SolverOutcome:
    """Build a plan: allocate loads, order stops, compute metrics and warnings."""

    started = perf_counter()
    active_trucks = [truck for truck in solver_input.trucks if truck.status is TruckStatus.ACTIVE]
    frozen = set(solver_input.frozen_order_ids)
    orders = [order for order in solver_input.orders if order.order_id not in frozen]

    index = LegIndex(solver_input.legs)
    allocation = allocate_loads(
        solver_input,
        orders,
        active_trucks,
        index,
        time_limit_sec,
        split_penalty_rub=solver_input.client_split_penalty_rub,
    )

    products = {product.product_id: product for product in solver_input.products}
    stocks = {(stock.warehouse_id, stock.product_id): stock for stock in solver_input.stocks}
    warehouses = {warehouse.warehouse_id: warehouse for warehouse in solver_input.warehouses}

    routes: list[PlannedRoute] = []
    for truck_load in allocation.truck_loads:
        warehouse = warehouses.get(truck_load.truck.warehouse_id)
        if warehouse is None:
            continue
        routes.append(
            build_route(
                RouteBuildContext(
                    truck=truck_load.truck,
                    warehouse=warehouse,
                    loads=tuple(
                        LoadedOrder(order=order, shipped_kg=kilograms)
                        for order, kilograms in truck_load.loads
                    ),
                    products=products,
                    stocks=stocks,
                    weather=solver_input.weather,
                    index=index,
                )
            )
        )

    metrics = _collect_metrics(
        routes,
        allocation,
        orders,
        {truck.truck_id: truck.capacity_kg for truck in active_trucks},
    )
    warnings = _collect_warnings(
        solver_input,
        orders,
        allocation,
        routes,
        active_trucks,
        metrics,
    )

    return SolverOutcome(
        routes=tuple(routes),
        metrics=metrics,
        warnings=tuple(warnings),
        allocation_method=allocation.method,
        elapsed_ms=round((perf_counter() - started) * 1000.0, 2),
    )


async def solve_async(
    solver_input: SolverInput,
    time_limit_sec: float = DEFAULT_SOLVER_TIME_LIMIT_SEC,
) -> SolverOutcome:
    """Run the CPU-bound solver outside the FastAPI event loop."""

    return await asyncio.to_thread(run_solver, solver_input, time_limit_sec)

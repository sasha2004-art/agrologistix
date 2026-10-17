"""Bio-logistics solver engine: allocation, routing, metrics and warnings.

``run_solver`` is a pure synchronous function so the whole plan can be computed
outside the event loop; :func:`solve_async` wraps it with ``asyncio.to_thread``
for FastAPI endpoints. The HiGHS time limit is bounded by the caller
(``SOLVER_TIME_LIMIT_SEC``) and the greedy fallback keeps the engine alive even
when the MILP hits that limit.
"""

import asyncio
from dataclasses import replace
from time import perf_counter

from app.schemas.enums import TruckStatus, WarningSeverity
from app.services.freshness_math import heat_limit_c
from app.services.solver_allocation import AllocationResult, allocate_loads
from app.services.solver_contract import (
    PlannedMetrics,
    PlannedRoute,
    PlannedStop,
    PlannedWarning,
    SolverFixedRoute,
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
from app.services.solver_improve import improve_allocation
from app.services.solver_limits import enforce_trip_limits
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
    # Internal MILP weight of undelivered cargo: kept for ``simulation_run``
    # telemetry, but not part of the public TCO (see ``PlannedMetrics``).
    unmet_penalty_rub = sum(
        kilograms * orders_by_id[order_id].penalty_per_kg
        for order_id, kilograms in allocation.unmet.items()
        if order_id in orders_by_id
    )
    requested_kg = sum(order.requested_kg for order in orders)
    # Расчёт везёт только фактически отгруженный груз: TCO — это доставка и
    # порча, а недовоз отвечает на вопрос «сколько не довезли» в процентах.
    total_tco_rub = trip_cost + spoilage_loss_rub
    avg_freshness_pct = (weighted_freshness / shipped_kg * 100.0) if shipped_kg > 0 else 0.0
    load_factor_pct = (shipped_kg / used_capacity_kg * 100.0) if used_capacity_kg > 0 else 0.0
    # Доля груза, испорченного в пути: 100 % минус средняя сохранность.
    spoilage_pct = 100.0 - avg_freshness_pct if shipped_kg > 0 else 0.0
    unmet_pct = (unmet_kg / requested_kg * 100.0) if requested_kg > 0 else 0.0

    return PlannedMetrics(
        total_tco_rub=round(total_tco_rub, 2),
        total_trip_cost_rub=round(trip_cost, 2),
        total_spoilage_loss_rub=round(spoilage_loss_rub, 2),
        total_unmet_penalty_rub=round(unmet_penalty_rub, 2),
        expected_net_profit_rub=round(revenue_rub - total_tco_rub, 2),
        avg_freshness_pct=round(min(100.0, max(0.0, avg_freshness_pct)), 2),
        spoilage_pct=round(min(100.0, max(0.0, spoilage_pct)), 2),
        unmet_pct=round(min(100.0, max(0.0, unmet_pct)), 2),
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
                message=f"Не в работе: {broken_count} — в расчёте не участвуют",
                severity=WarningSeverity.INFO.value,
            )
        )

    if not active_trucks and orders:
        warnings.append(
            PlannedWarning(
                code="no_active_trucks",
                message="Нет машин в строю: весь урожай остался не привезённым",
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
                    f"Не удалось привезти {metrics.unmet_kg:.0f} кг: не хватает машин, "
                    f"урожая на складе или подходящего транспорта"
                ),
                severity=severity,
            )
        )

    for order_id in sorted(allocation.unreachable_order_ids):
        order = orders_by_id[order_id]
        warnings.append(
            PlannedWarning(
                code="dirt_unreachable",
                message=(
                    "К этой точке не проехать: нужна машина, которая может ехать по грунтовке"
                ),
                severity=WarningSeverity.ERROR.value,
                client_id=order.client_id,
                order_id=order.order_id,
            )
        )

    temperature = solver_input.weather.temperature_c
    # Утеплённый кузов отодвигает порог порчи на +6 °C, рефрижератор порога не имеет.
    overheating = {
        truck.truck_id
        for truck in active_trucks
        if (limit := heat_limit_c(truck.has_reefer, truck.has_insulation)) is not None
        and temperature > limit
    }
    heat_risk = [route for route in routes if route.truck_id in overheating and route.stops]
    if heat_risk:
        warnings.append(
            PlannedWarning(
                code="heat_without_reefer",
                message=(
                    f"Жара +{temperature:.0f} °C: часть машин едет "
                    f"без охлаждения, урожай портится быстрее"
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
                        f"Урожая «{product.name or product.product_id}» не хватает: "
                        f"заказали {requested:.0f} кг, на складах "
                        f"{stock_by_product.get(product_id, 0.0):.0f} кг"
                    ),
                    severity=WarningSeverity.WARNING.value,
                )
            )

    return warnings


def _fixed_planned_routes(
    fixed_routes: tuple[SolverFixedRoute, ...],
    warehouses: dict[int, SolverWarehouse],
) -> list[PlannedRoute]:
    """Готовые рейсы фиксаций: один стоп, готовая геометрия и метрики."""

    planned: list[PlannedRoute] = []
    for fixed in fixed_routes:
        warehouse = warehouses.get(fixed.warehouse_id)
        origin = (
            (warehouse.latitude, warehouse.longitude)
            if warehouse is not None
            else (fixed.order.latitude, fixed.order.longitude)
        )
        geometry = fixed.geometry or (origin, (fixed.order.latitude, fixed.order.longitude))
        planned.append(
            PlannedRoute(
                truck_id=fixed.truck_id,
                truck_name=fixed.truck_name,
                warehouse_id=fixed.warehouse_id,
                total_distance_km=round(fixed.distance_km, 3),
                total_duration_min=round(fixed.duration_min, 2),
                total_cost_rub=round(fixed.trip_cost_rub, 2),
                geometry=tuple(geometry),
                stops=(
                    PlannedStop(
                        order_id=fixed.order.order_id,
                        truck_id=fixed.truck_id,
                        warehouse_id=fixed.warehouse_id,
                        client_id=fixed.order.client_id,
                        product_id=fixed.order.product_id,
                        sequence_order=1,
                        shipped_kg=round(fixed.shipped_kg, 3),
                        distance_km=round(fixed.distance_km, 3),
                        eta_minutes=round(fixed.duration_min, 2),
                        expected_freshness=round(fixed.expected_freshness, 6),
                        trip_leg_cost_rub=round(fixed.trip_cost_rub, 2),
                    ),
                ),
            )
        )
    return planned


def run_solver(
    solver_input: SolverInput,
    time_limit_sec: float = DEFAULT_SOLVER_TIME_LIMIT_SEC,
) -> SolverOutcome:
    """Build a plan: allocate loads, order stops, compute metrics and warnings."""

    started = perf_counter()
    # Фиксированные маршруты — уже выбранные логистом рейсы: их заявки не
    # перераспределяются, а машины не берутся в MILP повторно.
    fixed_routes = solver_input.fixed_routes
    fixed_truck_ids = {route.truck_id for route in fixed_routes}
    fixed_order_ids = {route.order.order_id for route in fixed_routes}
    active_trucks = [
        truck
        for truck in solver_input.trucks
        if truck.status is TruckStatus.ACTIVE and truck.truck_id not in fixed_truck_ids
    ]
    frozen = set(solver_input.frozen_order_ids)
    orders = [
        order
        for order in solver_input.orders
        if order.order_id not in frozen and order.order_id not in fixed_order_ids
    ]

    index = LegIndex(solver_input.legs)
    allocation = allocate_loads(
        solver_input,
        orders,
        active_trucks,
        index,
        time_limit_sec,
        split_penalty_rub=solver_input.client_split_penalty_rub,
    )
    # The MILP draft is priced with proxy costs; the local search rebuilds the
    # real routes and keeps the plan only when the true TCO gets better.
    allocation = improve_allocation(solver_input, allocation, orders, active_trucks, index)

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

    # Travel time and freshness depend on the stop order, so the end-of-shift
    # and freshness floors are enforced after routing. Dropped stops become
    # unmet demand with structured warnings (the improve stage may re-route
    # them later).
    orders_by_id = _orders_by_id(orders)
    limits = enforce_trip_limits(
        solver_input,
        tuple(routes),
        orders_by_id,
        unmet_kg_before=sum(allocation.unmet.values()),
    )
    if limits.rejected:
        merged_unmet = dict(allocation.unmet)
        for order_id, kilograms in limits.rejected.items():
            merged_unmet[order_id] = merged_unmet.get(order_id, 0.0) + kilograms
        allocation = replace(allocation, unmet=merged_unmet)
    routes = list(limits.routes)
    # Фиксированные рейсы добавляются после лимитов: они уже утверждены логистом.
    routes.extend(_fixed_planned_routes(fixed_routes, warehouses))

    metric_orders = [*orders, *(route.order for route in fixed_routes)]
    metrics = _collect_metrics(
        routes,
        allocation,
        metric_orders,
        {truck.truck_id: truck.capacity_kg for truck in solver_input.trucks},
    )
    warnings = _collect_warnings(
        solver_input,
        orders,
        allocation,
        routes,
        active_trucks,
        metrics,
    )
    warnings.extend(limits.warnings)

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

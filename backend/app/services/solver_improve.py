"""Local search over the real route TCO (stage 3 of the consolidation plan).

The MILP draft is scored with proxy costs, so it is only a starting point. This
module rebuilds the concrete routes, measures the real TCO (trip costs plus
spoilage plus unmet penalties and the client split price) and improves the plan
with deterministic first-improvement moves:

* ``merge`` — move every order of one trip into another trip, releasing a truck;
* ``relocate_client`` — collect all orders of one client on a single trip;
* ``move`` — move a single order to another trip;
* ``swap`` — exchange two orders between trips.

Every candidate must stay feasible: capacity, warehouse stock, dirt access and
the stop limit. The search stops at the first improving move, restarts from the
better plan and respects the evaluation/time budget, so
``POST /solver/optimize`` keeps its 1.5 s target. The MILP result is returned
untouched when no candidate improves the real TCO.
"""

import logging
from dataclasses import dataclass, replace
from time import perf_counter

from app.services.solver_allocation import (
    EPSILON,
    WEIGHT_PRECISION,
    AllocationResult,
    TruckLoad,
)
from app.services.solver_contract import (
    PlannedRoute,
    SolverInput,
    SolverOrder,
    SolverTruck,
    truck_can_serve_order,
)
from app.services.solver_routing import LegIndex, LoadedOrder, RouteBuildContext, build_route

logger = logging.getLogger(__name__)

TCO_EPSILON = 0.01
# Two orders of the same client may be split over several trucks, so moving a
# load must add the weights up instead of overwriting them.
LOAD_TOLERANCE_KG = 2e-3
LoadsMap = dict[int, dict[int, float]]


def _add_load(loads: dict[int, float], order_id: int, kilograms: float) -> None:
    """Accumulate one order share; never overwrite an existing share."""

    loads[order_id] = loads.get(order_id, 0.0) + kilograms


@dataclass(frozen=True, slots=True)
class Evaluation:
    """Real TCO of a plan plus how many client visits are split."""

    tco: float
    split_visits: int


@dataclass(frozen=True, slots=True)
class Plan:
    """Loads per truck plus unmet demand, ready for route rebuilding."""

    loads: tuple[tuple[int, tuple[tuple[int, float], ...]], ...]
    unmet: dict[int, float]

    @staticmethod
    def from_allocation(allocation: AllocationResult) -> "Plan":
        grouped: dict[int, dict[int, float]] = {}
        for truck_load in allocation.truck_loads:
            grouped[truck_load.truck.truck_id] = {
                order.order_id: kilograms for order, kilograms in truck_load.loads
            }
        return Plan.from_loads(grouped, dict(allocation.unmet))

    @staticmethod
    def from_loads(loads: LoadsMap, unmet: dict[int, float]) -> "Plan":
        packed = tuple(
            (truck_id, tuple(sorted(orders.items())))
            for truck_id, orders in sorted(loads.items())
            if orders
        )
        return Plan(loads=packed, unmet=dict(unmet))

    def to_loads(self) -> LoadsMap:
        return {truck_id: dict(orders) for truck_id, orders in self.loads}


class _Evaluator:
    """Rebuilds routes for a plan, measures real TCO and checks feasibility."""

    def __init__(
        self,
        solver_input: SolverInput,
        orders_by_id: dict[int, SolverOrder],
        truck_map: dict[int, SolverTruck],
        index: LegIndex,
    ) -> None:
        self.solver_input = solver_input
        self.orders_by_id = orders_by_id
        self.truck_map = truck_map
        self.index = index
        self.products = {product.product_id: product for product in solver_input.products}
        self.stocks = {
            (stock.warehouse_id, stock.product_id): stock for stock in solver_input.stocks
        }
        self.warehouses = {
            warehouse.warehouse_id: warehouse for warehouse in solver_input.warehouses
        }
        self._cache: dict[tuple[int, tuple[int, ...]], PlannedRoute | None] = {}
        self.route_builds = 0

    def _route(self, truck_id: int, quantities: dict[int, float]) -> PlannedRoute | None:
        key = (truck_id, tuple(sorted(quantities)))
        if key in self._cache:
            return self._cache[key]
        truck = self.truck_map.get(truck_id)
        warehouse = self.warehouses.get(truck.warehouse_id) if truck else None
        route: PlannedRoute | None = None
        if truck is not None and warehouse is not None:
            loads = tuple(
                LoadedOrder(order=self.orders_by_id[order_id], shipped_kg=kilograms)
                for order_id, kilograms in quantities.items()
            )
            route = build_route(
                RouteBuildContext(
                    truck=truck,
                    warehouse=warehouse,
                    loads=loads,
                    products=self.products,
                    stocks=self.stocks,
                    weather=self.solver_input.weather,
                    index=self.index,
                )
            )
        self._cache[key] = route
        self.route_builds += 1
        return route

    def routes(self, plan: Plan) -> list[PlannedRoute] | None:
        routes: list[PlannedRoute] = []
        for truck_id, orders in plan.loads:
            route = self._route(truck_id, dict(orders))
            if route is None:
                return None
            routes.append(route)
        return routes

    def evaluate(self, plan: Plan) -> Evaluation | None:
        """Build the routes once and return real TCO plus split visits."""

        routes = self.routes(plan)
        if routes is None:
            return None
        trip_cost = sum(route.total_cost_rub for route in routes)
        spoilage = 0.0
        visitors: dict[int, set[int]] = {}
        for route in routes:
            for stop in route.stops:
                order = self.orders_by_id.get(stop.order_id or -1)
                price = order.price_per_kg if order else 0.0
                spoilage += stop.shipped_kg * (1.0 - stop.expected_freshness) * price
                if order is not None:
                    visitors.setdefault(order.client_id, set()).add(route.truck_id)
        penalty = sum(
            kilograms * self.orders_by_id[order_id].penalty_per_kg
            for order_id, kilograms in plan.unmet.items()
            if order_id in self.orders_by_id
        )
        split_visits = sum(max(0, len(truck_ids) - 1) for truck_ids in visitors.values())
        return Evaluation(
            tco=(
                trip_cost
                + spoilage
                + penalty
                + split_visits * self.solver_input.client_split_penalty_rub
            ),
            split_visits=split_visits,
        )

    def tco(self, plan: Plan) -> float:
        evaluation = self.evaluate(plan)
        return float("inf") if evaluation is None else evaluation.tco

    def feasible(self, plan: Plan) -> bool:
        """Capacity, stock, dirt access, stop limit and full coverage of demand."""

        max_stops = self.solver_input.max_stops_per_trip
        stock_used: dict[tuple[int, int], float] = {}
        delivered: dict[int, float] = {}
        for truck_id, orders in plan.loads:
            truck = self.truck_map.get(truck_id)
            if truck is None or not orders or len(orders) > max_stops:
                return False
            total_kg = 0.0
            for order_id, kilograms in orders:
                order = self.orders_by_id.get(order_id)
                if order is None or kilograms <= EPSILON or not truck_can_serve_order(truck, order):
                    return False
                total_kg += kilograms
                delivered[order_id] = delivered.get(order_id, 0.0) + kilograms
                key = (truck.warehouse_id, order.product_id)
                stock_used[key] = stock_used.get(key, 0.0) + kilograms
            if total_kg > truck.capacity_kg + EPSILON:
                return False
        for key, kilograms in stock_used.items():
            stock = self.stocks.get(key)
            if stock is None or kilograms > stock.available_kg + EPSILON:
                return False
        # A candidate move must neither lose nor duplicate kilograms: every
        # order has to be fully covered by shipments plus unmet demand.
        for order_id, order in self.orders_by_id.items():
            total = delivered.get(order_id, 0.0) + plan.unmet.get(order_id, 0.0)
            if abs(total - order.requested_kg) > LOAD_TOLERANCE_KG:
                return False
        return True

    def within_shift(self, plan: Plan) -> bool:
        routes = self.routes(plan)
        if routes is None:
            return False
        max_minutes = self.solver_input.max_trip_hours * 60.0
        return all(
            not route.stops or route.stops[-1].eta_minutes <= max_minutes for route in routes
        )


def _merges(loads: LoadsMap) -> list[LoadsMap]:
    truck_ids = sorted(loads)
    candidates: list[LoadsMap] = []
    for position, source in enumerate(truck_ids):
        for target in truck_ids[position + 1 :]:
            merged = {truck_id: dict(orders) for truck_id, orders in loads.items()}
            for order_id, kilograms in merged.pop(source).items():
                _add_load(merged[target], order_id, kilograms)
            candidates.append(merged)
    return candidates


def _client_moves(loads: LoadsMap, orders_by_id: dict[int, SolverOrder]) -> list[LoadsMap]:
    clients: dict[int, list[int]] = {}
    for orders in loads.values():
        for order_id in orders:
            order = orders_by_id.get(order_id)
            if order is not None:
                clients.setdefault(order.client_id, []).append(order_id)

    candidates: list[LoadsMap] = []
    for order_ids in clients.values():
        sources = {truck_id for truck_id, orders in loads.items() if set(order_ids) & set(orders)}
        if len(sources) < 2:
            continue
        for target in sorted(loads):
            moved = {truck_id: dict(orders) for truck_id, orders in loads.items()}
            for order_id in order_ids:
                for truck_id in list(moved):
                    if truck_id != target and order_id in moved[truck_id]:
                        _add_load(moved[target], order_id, moved[truck_id].pop(order_id))
            candidates.append({truck_id: orders for truck_id, orders in moved.items() if orders})
    return candidates


def _single_moves(loads: LoadsMap) -> list[LoadsMap]:
    truck_ids = sorted(loads)
    candidates: list[LoadsMap] = []
    for source in truck_ids:
        for order_id in sorted(loads[source]):
            for target in truck_ids:
                if target == source:
                    continue
                moved = {truck_id: dict(orders) for truck_id, orders in loads.items()}
                _add_load(moved[target], order_id, moved[source].pop(order_id))
                candidates.append(
                    {truck_id: orders for truck_id, orders in moved.items() if orders}
                )
    return candidates


def _swaps(loads: LoadsMap) -> list[LoadsMap]:
    truck_ids = sorted(loads)
    candidates: list[LoadsMap] = []
    for position, first in enumerate(truck_ids):
        for second in truck_ids[position + 1 :]:
            for order_first in sorted(loads[first]):
                for order_second in sorted(loads[second]):
                    swapped = {truck_id: dict(orders) for truck_id, orders in loads.items()}
                    kilograms_first = swapped[first].pop(order_first)
                    kilograms_second = swapped[second].pop(order_second)
                    _add_load(swapped[first], order_second, kilograms_second)
                    _add_load(swapped[second], order_first, kilograms_first)
                    candidates.append(
                        {truck_id: orders for truck_id, orders in swapped.items() if orders}
                    )
    return candidates


def improve_allocation(
    solver_input: SolverInput,
    allocation: AllocationResult,
    orders: list[SolverOrder],
    trucks: list[SolverTruck],
    index: LegIndex,
) -> AllocationResult:
    """Improve the MILP draft with a deterministic local search over real TCO."""

    if not allocation.truck_loads or not trucks:
        return allocation

    orders_by_id = {order.order_id: order for order in orders}
    truck_map = {truck.truck_id: truck for truck in trucks}
    evaluator = _Evaluator(solver_input, orders_by_id, truck_map, index)
    plan = Plan.from_allocation(allocation)
    best_tco = evaluator.tco(plan)
    if best_tco == float("inf") or not evaluator.feasible(plan) or not evaluator.within_shift(plan):
        return allocation

    budget_end = perf_counter() + solver_input.improve_time_budget_sec
    evaluations = 0
    improved_plan: Plan | None = None
    current = evaluator.evaluate(plan)
    if current is None:
        return allocation
    while evaluations < solver_input.improve_max_evaluations and perf_counter() < budget_end:
        moved = False
        for factory in (_merges, _client_moves, _single_moves, _swaps):
            loads = plan.to_loads()
            candidates = (
                _client_moves(loads, orders_by_id) if factory is _client_moves else factory(loads)
            )
            for candidate_loads in candidates:
                evaluations += 1
                if (
                    evaluations >= solver_input.improve_max_evaluations
                    or perf_counter() >= budget_end
                ):
                    break
                candidate = Plan.from_loads(candidate_loads, plan.unmet)
                if not evaluator.feasible(candidate):
                    continue
                candidate_evaluation = evaluator.evaluate(candidate)
                if candidate_evaluation is None:
                    continue
                # Consolidation never gets worse: a move may merge client
                # visits, but it must not scatter a shop over more trucks.
                if candidate_evaluation.split_visits > current.split_visits:
                    continue
                if candidate_evaluation.tco < current.tco - TCO_EPSILON and evaluator.within_shift(
                    candidate
                ):
                    plan, current, improved_plan = candidate, candidate_evaluation, candidate
                    moved = True
                    break
            if moved:
                break
        if not moved:
            break

    if improved_plan is None:
        return allocation

    logger.info(
        "Route consolidation improved the plan: evaluations=%s, route_builds=%s, tco=%.2f, "
        "split_visits=%s",
        evaluations,
        evaluator.route_builds,
        current.tco,
        current.split_visits,
    )
    return _to_allocation(improved_plan, allocation, truck_map, orders_by_id)


def _to_allocation(
    plan: Plan,
    source: AllocationResult,
    truck_map: dict[int, SolverTruck],
    orders_by_id: dict[int, SolverOrder],
) -> AllocationResult:
    truck_loads: list[TruckLoad] = []
    for truck_id, orders in plan.loads:
        truck = truck_map.get(truck_id)
        if truck is None:
            continue
        loads = tuple(
            (orders_by_id[order_id], round(kilograms, WEIGHT_PRECISION))
            for order_id, kilograms in orders
            if order_id in orders_by_id
        )
        if loads:
            truck_loads.append(TruckLoad(truck=truck, loads=loads))
    return replace(
        source,
        truck_loads=tuple(truck_loads),
        unmet={order_id: round(kg, WEIGHT_PRECISION) for order_id, kg in plan.unmet.items()},
        method=f"{source.method}+improved",
    )

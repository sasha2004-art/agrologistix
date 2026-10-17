"""Route construction: leg lookup, 2-opt ordering, ETA and freshness per stop."""

from collections.abc import Callable, Sequence
from dataclasses import dataclass

from app.services.distance_matrix import Coordinate, fallback_leg
from app.services.freshness_math import (
    CargoProfile,
    freshness_after_hours,
    precipitation_factor,
    surface_factor,
)
from app.services.solver_contract import (
    PlannedRoute,
    PlannedStop,
    SolverLeg,
    SolverOrder,
    SolverProduct,
    SolverStock,
    SolverTruck,
    SolverWarehouse,
    SolverWeather,
)

Point = tuple[float, float]
DistanceFn = Callable[[Point, Point], float]

CACHE_PRECISION = 5
TWO_OPT_MAX_PASSES = 20


def _normalize(value: float) -> float:
    rounded = round(value, CACHE_PRECISION)
    return 0.0 if rounded == 0 else rounded


def point_key(point: Point) -> str:
    lat, lon = point
    return f"{_normalize(lat):.5f}_{_normalize(lon):.5f}"


class LegIndex:
    """Lookup of cached legs with a haversine fallback for missing pairs.

    Fallback legs are memoized: the local search rebuilds routes hundreds of
    times, and recomputing the same haversine polyline would waste CPU on the
    single-vCPU target host.
    """

    def __init__(self, legs: Sequence[SolverLeg]) -> None:
        self._legs = {(point_key(leg.origin), point_key(leg.destination)): leg for leg in legs}
        self._fallback_cache: dict[tuple[str, str], SolverLeg] = {}

    def leg(self, origin: Point, destination: Point) -> SolverLeg | None:
        return self._legs.get((point_key(origin), point_key(destination)))

    def _fallback(self, origin: Point, destination: Point):
        key = (point_key(origin), point_key(destination))
        cached = self._fallback_cache.get(key)
        if cached is not None:
            return cached
        leg = fallback_leg(
            Coordinate(lat=origin[0], lon=origin[1]),
            Coordinate(lat=destination[0], lon=destination[1]),
        )
        self._fallback_cache[key] = leg
        return leg

    def distance_km(self, origin: Point, destination: Point) -> float:
        leg = self.leg(origin, destination)
        if leg is not None:
            return leg.distance_km
        return self._fallback(origin, destination).distance_km

    def geometry(self, origin: Point, destination: Point) -> list[Point]:
        leg = self.leg(origin, destination)
        if leg is not None and leg.geometry:
            return list(leg.geometry)
        return self._fallback(origin, destination).geometry


def nearest_neighbour_order(
    origin: Point, points: Sequence[Point], distance: DistanceFn
) -> list[int]:
    """Greedy initial order: positions sorted by the closest unvisited point."""

    remaining = list(range(len(points)))
    ordered: list[int] = []
    current = origin
    while remaining:
        closest = min(remaining, key=lambda position: distance(current, points[position]))
        ordered.append(closest)
        remaining.remove(closest)
        current = points[closest]
    return ordered


def two_opt_order(
    origin: Point, points: Sequence[Point], order: Sequence[int], distance: DistanceFn
) -> list[int]:
    """Improve an open route (origin is the fixed depot) with 2-opt swaps.

    Positions are returned instead of points so that several orders of the same
    client (identical coordinates) keep their own stops.

    Reversing a segment also flips the direction of every inner link. Road legs
    are directional (Mapbox distances can differ per direction), so the classic
    two-edge delta is invalid here: the whole candidate route is measured and the
    reversal is kept only when the exact length improves. Routes are short
    (``max_stops_per_trip``), so the full recalculation stays cheap.
    """

    route = list(order)
    if len(route) < 3:
        return route

    def route_length(candidate: Sequence[int]) -> float:
        total = 0.0
        current = origin
        for position in candidate:
            point = points[position]
            total += distance(current, point)
            current = point
        return total

    best_length = route_length(route)
    for _ in range(TWO_OPT_MAX_PASSES):
        improved = False
        for start in range(len(route) - 1):
            for end in range(start + 1, len(route)):
                candidate = route[:start] + route[start : end + 1][::-1] + route[end + 1 :]
                candidate_length = route_length(candidate)
                if candidate_length + 1e-9 < best_length:
                    route = candidate
                    best_length = candidate_length
                    improved = True
        if not improved:
            break
    return route


@dataclass(frozen=True, slots=True)
class LoadedOrder:
    order: SolverOrder
    shipped_kg: float


@dataclass(frozen=True, slots=True)
class RouteBuildContext:
    truck: SolverTruck
    warehouse: SolverWarehouse
    loads: tuple[LoadedOrder, ...]
    products: dict[int, SolverProduct]
    stocks: dict[tuple[int, int], SolverStock]
    weather: SolverWeather
    index: LegIndex


def _client_point(order: SolverOrder) -> Point:
    return (order.latitude, order.longitude)


def _merge_geometry(geometry: list[Point], segment: Sequence[Point]) -> None:
    for point in segment:
        if geometry and point_key(geometry[-1]) == point_key(point):
            continue
        geometry.append(point)


def build_route(context: RouteBuildContext) -> PlannedRoute:
    """Order the assigned orders with 2-opt and compute stops, ETA and freshness."""

    truck = context.truck
    origin = (context.warehouse.latitude, context.warehouse.longitude)

    distance_fn: DistanceFn = context.index.distance_km
    loads = list(context.loads)
    client_points = [_client_point(load.order) for load in loads]
    initial_order = nearest_neighbour_order(origin, client_points, distance_fn)
    ordered_positions = two_opt_order(origin, client_points, initial_order, distance_fn)

    stops: list[PlannedStop] = []
    geometry: list[Point] = [origin]
    previous = origin
    travelled_km = 0.0
    travelled_hours = 0.0
    trip_cost_rub = 0.0

    for sequence, position in enumerate(ordered_positions, start=1):
        load = loads[position]
        order = load.order
        point = client_points[position]
        segment_km = context.index.distance_km(previous, point)
        segment_hours = (
            segment_km
            / truck.cruise_speed_kmh
            * surface_factor(order.road_type)
            * precipitation_factor(context.weather.precipitation_mm)
        )
        travelled_km += segment_km
        travelled_hours += segment_hours

        stock = context.stocks.get((truck.warehouse_id, order.product_id))
        product = context.products[order.product_id]
        cargo = CargoProfile(
            spoilage_rate=product.spoilage_rate,
            initial_freshness=stock.initial_freshness if stock else 1.0,
            price_per_kg=order.price_per_kg,
        )
        freshness = freshness_after_hours(
            cargo,
            travelled_hours,
            context.weather.temperature_c,
            truck.has_reefer,
            truck.has_insulation,
        )

        segment_cost = segment_km * truck.cost_per_km_rub
        if sequence == 1:
            segment_cost += truck.fixed_trip_cost_rub
        trip_cost_rub += segment_cost

        stops.append(
            PlannedStop(
                order_id=order.order_id,
                truck_id=truck.truck_id,
                warehouse_id=truck.warehouse_id,
                client_id=order.client_id,
                product_id=order.product_id,
                sequence_order=sequence,
                shipped_kg=load.shipped_kg,
                distance_km=round(segment_km, 3),
                eta_minutes=round(travelled_hours * 60.0, 2),
                expected_freshness=round(freshness, 6),
                trip_leg_cost_rub=round(segment_cost, 2),
                price_per_kg=order.price_per_kg,
            )
        )

        _merge_geometry(geometry, context.index.geometry(previous, point))
        previous = point

    return PlannedRoute(
        truck_id=truck.truck_id,
        truck_name=truck.name,
        warehouse_id=truck.warehouse_id,
        total_distance_km=round(travelled_km, 3),
        total_duration_min=round(travelled_hours * 60.0, 2),
        total_cost_rub=round(trip_cost_rub, 2),
        geometry=tuple(geometry),
        stops=tuple(stops),
    )

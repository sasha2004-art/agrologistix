"""Input/output contract of the bio-logistics solver engine.

Day 6 fixes the data contract only. The MILP distribution (SciPy HiGHS),
capacity and dirt-road constraints, 2-opt stop ordering, ``asyncio.to_thread``
execution and persistence are implemented on Day 7-8 inside this module.

Input format (:class:`SolverInput`)
-----------------------------------
Everything the engine may read is passed explicitly, so the solver stays pure and
testable:

* ``products`` — crop spoilage rates ``lambda_p`` and base costs;
* ``stocks`` — available kilograms per ``(warehouse_id, product_id)`` pair;
* ``orders`` — pending client demand with price, unmet penalty and road type;
* ``trucks`` — only ``active`` fleet units with capacity, cruise speed, reefer
  and dirt road permission;
* ``legs`` — distance, base duration and geometry per ordered coordinate pair
  (from ``app.services.distance_matrix``);
* ``weather`` — temperature and precipitation used by ``app.services.freshness_math``;
* ``frozen_order_ids`` — orders already marked ``delivered``; they are never
  reassigned, but their shipments stay in the "before" side of a comparison.

Output format
-------------
The engine returns ``app.schemas.solver_schemas.SolverResponse`` (converted from
internal dataclasses by the API layer):

* ``routes[]`` — one entry per truck with ``truck_id``, ``warehouse_id``,
  ordered ``stops[]`` (``order_id``, ``client_id``, ``product_id``,
  ``sequence_order``, ``shipped_kg``, ``distance_km``, ``eta_minutes``,
  ``expected_freshness``, ``trip_leg_cost_rub``), total distance/duration/cost
  and a ``geometry`` polyline of ``(lat, lon)`` points;
* ``metrics`` — TCO parts (trip cost, spoilage loss, unmet penalty), expected
  net profit, average freshness percentage, shipped and unmet kilograms;
* ``warnings[]`` — structured warnings such as an unreachable dirt road client
  (``code``, ``message``, ``severity``, ``client_id``, ``order_id``);
* ``comparison`` — optional ``ComparisonDelta`` against ``baseline_run_id``.

Hard constraints encoded in the contract:

1. a truck with ``can_use_dirt = False`` is never assigned to an order with
   ``road_type = 'dirt'``;
2. the sum of ``shipped_kg`` in one route never exceeds ``capacity_kg``;
3. shipments of product ``p`` from warehouse ``w`` never exceed stock;
4. frozen (``delivered``) orders are never reassigned;
5. every scenario stays feasible: unmet demand is a slack variable with
   ``penalty_per_kg``.
"""

from dataclasses import dataclass, field

from app.schemas.enums import RoadType


@dataclass(frozen=True, slots=True)
class SolverProduct:
    product_id: int
    spoilage_rate: float
    base_cost_rub: float


@dataclass(frozen=True, slots=True)
class SolverStock:
    warehouse_id: int
    product_id: int
    available_kg: float


@dataclass(frozen=True, slots=True)
class SolverOrder:
    order_id: int
    client_id: int
    product_id: int
    requested_kg: float
    price_per_kg: float
    penalty_per_kg: float
    road_type: RoadType
    latitude: float
    longitude: float


@dataclass(frozen=True, slots=True)
class SolverTruck:
    truck_id: int
    name: str
    warehouse_id: int
    capacity_kg: float
    cruise_speed_kmh: float
    cost_per_km_rub: float
    fixed_trip_cost_rub: float
    has_reefer: bool
    can_use_dirt: bool


@dataclass(frozen=True, slots=True)
class SolverLeg:
    """Distance and geometry of one ordered coordinate pair."""

    origin: tuple[float, float]
    destination: tuple[float, float]
    distance_km: float
    base_duration_min: float


@dataclass(frozen=True, slots=True)
class SolverWeather:
    temperature_c: float
    precipitation_mm: float
    mode: str


@dataclass(frozen=True, slots=True)
class SolverInput:
    products: tuple[SolverProduct, ...]
    stocks: tuple[SolverStock, ...]
    orders: tuple[SolverOrder, ...]
    trucks: tuple[SolverTruck, ...]
    legs: tuple[SolverLeg, ...]
    weather: SolverWeather
    frozen_order_ids: tuple[int, ...] = field(default_factory=tuple)


def truck_can_serve_order(truck: SolverTruck, order: SolverOrder) -> bool:
    """Hard constraint 1: a heavy truck never enters a dirt road approach."""

    return order.road_type is not RoadType.DIRT or truck.can_use_dirt

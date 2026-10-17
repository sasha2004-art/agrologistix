"""Input/output contract of the bio-logistics solver engine.

The engine itself is a pure function: all data is passed explicitly through
:class:`SolverInput` and the result is returned as :class:`SolverOutcome`
without touching the database. The API layer converts the outcome into
``app.schemas.solver_schemas.SolverResponse`` and persists routes.

Input
-----
* ``warehouses`` — coordinates used as route origins;
* ``products`` — crop spoilage rates ``lambda_p`` and base costs;
* ``stocks`` — available kilograms per ``(warehouse_id, product_id)`` pair;
* ``orders`` — pending client demand with price, unmet penalty and road type;
* ``trucks`` — fleet units; ``status`` other than ``active`` is ignored;
* ``legs`` — distance, base duration and geometry per ordered coordinate pair;
* ``weather`` — temperature and precipitation used by ``freshness_math``;
* ``frozen_order_ids`` — orders already marked ``delivered``; they are never
  reassigned and never counted as unmet demand.

Output
------
:class:`SolverOutcome` carries planned routes with ordered stops, metrics and
structured warnings. Route geometry starts at the warehouse and follows the stop
order, using cached polylines with intermediate nodes or a straight fallback.

Hard constraints encoded in the engine:

1. a truck with ``can_use_dirt = False`` is never assigned to a ``dirt`` order;
2. the sum of ``shipped_kg`` in one route never exceeds ``capacity_kg``;
3. shipments of product ``p`` from warehouse ``w`` never exceed stock;
4. frozen (``delivered``) orders are never reassigned;
5. broken trucks are never used;
6. every scenario stays feasible: unmet demand is a slack variable with
   ``penalty_per_kg``.
"""

from dataclasses import dataclass, field

from app.schemas.enums import RoadType, StopStatus, TruckStatus, WarningSeverity


@dataclass(frozen=True, slots=True)
class SolverWarehouse:
    warehouse_id: int
    name: str
    latitude: float
    longitude: float


@dataclass(frozen=True, slots=True)
class SolverProduct:
    product_id: int
    spoilage_rate: float
    base_cost_rub: float
    name: str = ""


@dataclass(frozen=True, slots=True)
class SolverStock:
    warehouse_id: int
    product_id: int
    available_kg: float
    initial_freshness: float = 1.0


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
    status: TruckStatus = TruckStatus.ACTIVE


@dataclass(frozen=True, slots=True)
class SolverLeg:
    """Distance, duration and geometry of one ordered coordinate pair."""

    origin: tuple[float, float]
    destination: tuple[float, float]
    distance_km: float
    base_duration_min: float
    geometry: tuple[tuple[float, float], ...] = field(default_factory=tuple)


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
    warehouses: tuple[SolverWarehouse, ...] = field(default_factory=tuple)
    frozen_order_ids: tuple[int, ...] = field(default_factory=tuple)
    # Price of splitting one client over several trucks (soft grouping mode).
    client_split_penalty_rub: float = 0.0


@dataclass(frozen=True, slots=True)
class PlannedStop:
    """One delivery point of a planned route (mirrors ``RouteStopResponse``)."""

    order_id: int | None
    truck_id: int
    warehouse_id: int
    client_id: int
    product_id: int
    sequence_order: int
    shipped_kg: float
    distance_km: float
    eta_minutes: float
    expected_freshness: float
    trip_leg_cost_rub: float
    stop_status: str = StopStatus.PLANNED.value


@dataclass(frozen=True, slots=True)
class PlannedRoute:
    truck_id: int
    truck_name: str
    warehouse_id: int
    total_distance_km: float
    total_duration_min: float
    total_cost_rub: float
    geometry: tuple[tuple[float, float], ...]
    stops: tuple[PlannedStop, ...]


@dataclass(frozen=True, slots=True)
class PlannedMetrics:
    total_tco_rub: float
    total_trip_cost_rub: float
    total_spoilage_loss_rub: float
    total_unmet_penalty_rub: float
    expected_net_profit_rub: float
    avg_freshness_pct: float
    shipped_kg: float
    unmet_kg: float
    # Route consolidation telemetry: how many trips the plan uses, how full the
    # trucks are and how many clients are served by more than one trip.
    total_trips: int = 0
    avg_load_factor_pct: float = 0.0
    split_clients: int = 0


@dataclass(frozen=True, slots=True)
class PlannedWarning:
    code: str
    message: str
    severity: str = WarningSeverity.WARNING.value
    client_id: int | None = None
    order_id: int | None = None


@dataclass(frozen=True, slots=True)
class SolverOutcome:
    routes: tuple[PlannedRoute, ...]
    metrics: PlannedMetrics
    warnings: tuple[PlannedWarning, ...]
    allocation_method: str = "milp"
    elapsed_ms: float = 0.0


def truck_can_serve_order(truck: SolverTruck, order: SolverOrder) -> bool:
    """Hard constraint 1: a heavy truck never enters a dirt road approach."""

    return order.road_type is not RoadType.DIRT or truck.can_use_dirt

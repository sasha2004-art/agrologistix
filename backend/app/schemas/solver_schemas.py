from pydantic import Field

from app.schemas.base import APIModel
from app.schemas.enums import StopStatus, WarningSeverity


class SolverRequest(APIModel):
    """The plan is always rebuilt from the current ERP state.

    There is no scenario switch: the logist changes orders/trucks/weather via
    ``PATCH`` and asks the solver again, so the request carries no fields.
    """


class SolverWarning(APIModel):
    code: str
    message: str
    severity: WarningSeverity = WarningSeverity.WARNING
    client_id: int | None = Field(default=None, gt=0)
    order_id: int | None = Field(default=None, gt=0)


class RoutePoint(APIModel):
    lat: float
    lon: float


class RouteStopResponse(APIModel):
    order_id: int | None = Field(default=None, gt=0)
    truck_id: int = Field(gt=0)
    warehouse_id: int = Field(gt=0)
    client_id: int = Field(gt=0)
    product_id: int = Field(gt=0)
    sequence_order: int = Field(ge=1)
    shipped_kg: float = Field(ge=0.0)
    distance_km: float = Field(ge=0.0)
    eta_minutes: float = Field(ge=0.0)
    expected_freshness: float = Field(ge=0.0, le=1.0)
    trip_leg_cost_rub: float = Field(ge=0.0)
    stop_status: StopStatus = StopStatus.PLANNED


class RouteResponse(APIModel):
    truck_id: int = Field(gt=0)
    truck_name: str
    warehouse_id: int = Field(gt=0)
    total_distance_km: float = Field(ge=0.0)
    total_duration_min: float = Field(ge=0.0)
    total_cost_rub: float = Field(ge=0.0)
    geometry: list[RoutePoint] = Field(default_factory=list)
    stops: list[RouteStopResponse] = Field(default_factory=list)


class Metrics(APIModel):
    """Публичные метрики плана: доставка и потери урожая, без штрафов.

    Недовоз измеряется килограммами и процентом от заказанного
    (``unmet_kg`` / ``unmet_pct``), испорченный в пути груз — процентом
    ``spoilage_pct``. Внутренний вес недовоза MILP наружу не отдаётся.
    """

    total_tco_rub: float = Field(ge=0.0)
    total_trip_cost_rub: float = Field(ge=0.0)
    total_spoilage_loss_rub: float = Field(ge=0.0)
    expected_net_profit_rub: float
    avg_freshness_pct: float = Field(ge=0.0, le=100.0)
    spoilage_pct: float = Field(ge=0.0, le=100.0)
    unmet_pct: float = Field(ge=0.0, le=100.0)
    shipped_kg: float = Field(ge=0.0)
    unmet_kg: float = Field(ge=0.0)
    # Route consolidation telemetry.
    total_trips: int = Field(default=0, ge=0)
    avg_load_factor_pct: float = Field(default=0.0, ge=0.0, le=100.0)
    split_clients: int = Field(default=0, ge=0)


class SolverResponse(APIModel):
    run_id: int = Field(gt=0)
    routes: list[RouteResponse] = Field(default_factory=list)
    metrics: Metrics
    warnings: list[SolverWarning] = Field(default_factory=list)

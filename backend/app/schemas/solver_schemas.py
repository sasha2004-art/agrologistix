from pydantic import Field, model_validator

from app.schemas.base import APIModel
from app.schemas.enums import SolverMode, StopStatus, WarningSeverity


class SolverRequest(APIModel):
    mode: SolverMode
    baseline_run_id: int | None = Field(default=None, gt=0)

    @model_validator(mode="after")
    def validate_baseline_reference(self) -> "SolverRequest":
        if self.mode is SolverMode.WHAT_IF and self.baseline_run_id is None:
            raise ValueError("baseline_run_id is required for what_if mode")
        return self


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
    total_tco_rub: float = Field(ge=0.0)
    total_trip_cost_rub: float = Field(ge=0.0)
    total_spoilage_loss_rub: float = Field(ge=0.0)
    total_unmet_penalty_rub: float = Field(ge=0.0)
    expected_net_profit_rub: float
    avg_freshness_pct: float = Field(ge=0.0, le=100.0)
    shipped_kg: float = Field(ge=0.0)
    unmet_kg: float = Field(ge=0.0)


class MetricDelta(APIModel):
    before: float
    after: float
    delta: float
    delta_pct: float | None = None


class ComparisonDelta(APIModel):
    total_tco_rub: MetricDelta
    total_trip_cost_rub: MetricDelta
    total_spoilage_loss_rub: MetricDelta
    total_unmet_penalty_rub: MetricDelta
    expected_net_profit_rub: MetricDelta
    avg_freshness_pct: MetricDelta
    shipped_kg: MetricDelta
    unmet_kg: MetricDelta


class SolverResponse(APIModel):
    run_id: int = Field(gt=0)
    parent_run_id: int | None = Field(default=None, gt=0)
    routes: list[RouteResponse] = Field(default_factory=list)
    metrics: Metrics
    warnings: list[SolverWarning] = Field(default_factory=list)
    comparison: ComparisonDelta | None = None

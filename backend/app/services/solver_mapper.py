"""Convert the internal solver outcome into the public API DTOs."""

from dataclasses import dataclass

from app.schemas.solver_schemas import (
    ComparisonDelta,
    MetricDelta,
    Metrics,
    RoutePoint,
    RouteResponse,
    RouteStopResponse,
    SolverResponse,
    SolverWarning,
)
from app.services.solver_contract import SolverOutcome


@dataclass(frozen=True, slots=True)
class BaselineMetrics:
    """Metric snapshot of a stored baseline run used for the what-if delta."""

    total_tco_rub: float
    total_trip_cost_rub: float
    total_spoilage_loss_rub: float
    total_unmet_penalty_rub: float
    expected_net_profit_rub: float
    avg_freshness_pct: float
    shipped_kg: float
    unmet_kg: float
    total_trips: int = 0
    avg_load_factor_pct: float = 0.0
    split_clients: int = 0


def _metric_delta(before: float, after: float) -> MetricDelta:
    delta = after - before
    delta_pct = (delta / before * 100.0) if before != 0 else None
    return MetricDelta(
        before=round(before, 2),
        after=round(after, 2),
        delta=round(delta, 2),
        delta_pct=None if delta_pct is None else round(delta_pct, 2),
    )


def build_comparison(before: BaselineMetrics, outcome: SolverOutcome) -> ComparisonDelta:
    """Build the \"before / after\" delta between a baseline run and a new plan."""

    after = outcome.metrics
    return ComparisonDelta(
        total_tco_rub=_metric_delta(before.total_tco_rub, after.total_tco_rub),
        total_trip_cost_rub=_metric_delta(before.total_trip_cost_rub, after.total_trip_cost_rub),
        total_spoilage_loss_rub=_metric_delta(
            before.total_spoilage_loss_rub, after.total_spoilage_loss_rub
        ),
        total_unmet_penalty_rub=_metric_delta(
            before.total_unmet_penalty_rub, after.total_unmet_penalty_rub
        ),
        expected_net_profit_rub=_metric_delta(
            before.expected_net_profit_rub, after.expected_net_profit_rub
        ),
        avg_freshness_pct=_metric_delta(before.avg_freshness_pct, after.avg_freshness_pct),
        shipped_kg=_metric_delta(before.shipped_kg, after.shipped_kg),
        unmet_kg=_metric_delta(before.unmet_kg, after.unmet_kg),
        total_trips=_metric_delta(before.total_trips, after.total_trips),
        avg_load_factor_pct=_metric_delta(before.avg_load_factor_pct, after.avg_load_factor_pct),
        split_clients=_metric_delta(before.split_clients, after.split_clients),
    )


def to_solver_response(
    outcome: SolverOutcome,
    run_id: int,
    parent_run_id: int | None = None,
    comparison: ComparisonDelta | None = None,
) -> SolverResponse:
    """Map engine dataclasses to ``SolverResponse`` without changing the schema."""

    routes = [
        RouteResponse(
            truck_id=route.truck_id,
            truck_name=route.truck_name,
            warehouse_id=route.warehouse_id,
            total_distance_km=route.total_distance_km,
            total_duration_min=route.total_duration_min,
            total_cost_rub=route.total_cost_rub,
            geometry=[RoutePoint(lat=lat, lon=lon) for lat, lon in route.geometry],
            stops=[
                RouteStopResponse(
                    order_id=stop.order_id,
                    truck_id=stop.truck_id,
                    warehouse_id=stop.warehouse_id,
                    client_id=stop.client_id,
                    product_id=stop.product_id,
                    sequence_order=stop.sequence_order,
                    shipped_kg=stop.shipped_kg,
                    distance_km=stop.distance_km,
                    eta_minutes=stop.eta_minutes,
                    expected_freshness=stop.expected_freshness,
                    trip_leg_cost_rub=stop.trip_leg_cost_rub,
                    stop_status=stop.stop_status,
                )
                for stop in route.stops
            ],
        )
        for route in outcome.routes
    ]

    metrics = Metrics(
        total_tco_rub=outcome.metrics.total_tco_rub,
        total_trip_cost_rub=outcome.metrics.total_trip_cost_rub,
        total_spoilage_loss_rub=outcome.metrics.total_spoilage_loss_rub,
        total_unmet_penalty_rub=outcome.metrics.total_unmet_penalty_rub,
        expected_net_profit_rub=outcome.metrics.expected_net_profit_rub,
        avg_freshness_pct=outcome.metrics.avg_freshness_pct,
        shipped_kg=outcome.metrics.shipped_kg,
        unmet_kg=outcome.metrics.unmet_kg,
        total_trips=outcome.metrics.total_trips,
        avg_load_factor_pct=outcome.metrics.avg_load_factor_pct,
        split_clients=outcome.metrics.split_clients,
    )

    warnings = [
        SolverWarning(
            code=warning.code,
            message=warning.message,
            severity=warning.severity,
            client_id=warning.client_id,
            order_id=warning.order_id,
        )
        for warning in outcome.warnings
    ]

    return SolverResponse(
        run_id=run_id,
        parent_run_id=parent_run_id,
        routes=routes,
        metrics=metrics,
        warnings=warnings,
        comparison=comparison,
    )

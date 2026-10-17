"""Convert the internal solver outcome into the public API DTOs."""

from app.schemas.solver_schemas import (
    Metrics,
    RoutePoint,
    RouteResponse,
    RouteStopResponse,
    SolverResponse,
    SolverWarning,
)
from app.services.solver_contract import SolverOutcome


def to_solver_response(outcome: SolverOutcome, run_id: int) -> SolverResponse:
    """Map engine dataclasses to ``SolverResponse``."""

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

    # ``total_unmet_penalty_rub`` намеренно не попадает в публичный DTO:
    # это внутренний вес недовоза в MILP, а не штраф для пользователя.
    metrics = Metrics(
        total_tco_rub=outcome.metrics.total_tco_rub,
        total_trip_cost_rub=outcome.metrics.total_trip_cost_rub,
        total_spoilage_loss_rub=outcome.metrics.total_spoilage_loss_rub,
        expected_net_profit_rub=outcome.metrics.expected_net_profit_rub,
        avg_freshness_pct=outcome.metrics.avg_freshness_pct,
        spoilage_pct=outcome.metrics.spoilage_pct,
        unmet_pct=outcome.metrics.unmet_pct,
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
        routes=routes,
        metrics=metrics,
        warnings=warnings,
    )

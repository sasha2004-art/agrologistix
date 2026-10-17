from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlmodel import Session, select

from app.core.config import Settings, get_settings
from app.core.database import get_session
from app.core.security import AccessContext
from app.models.erp_models import Truck
from app.models.run_models import RouteStop, SimulationRun
from app.schemas.enums import SolverMode
from app.schemas.error_schemas import APIErrorResponse
from app.schemas.solver_schemas import ComparisonDelta, SolverRequest, SolverResponse
from app.services.solver_engine import SolverOutcome, solve_async
from app.services.solver_input import build_solver_input
from app.services.solver_mapper import (
    BaselineMetrics,
    build_comparison,
    to_solver_response,
)
from app.services.weather_service import WeatherSnapshot, get_current_weather

router = APIRouter(prefix="/solver", tags=["solver"])

SessionDependency = Annotated[Session, Depends(get_session)]
SettingsDependency = Annotated[Settings, Depends(get_settings)]

_NOT_FOUND_RESPONSE = {"model": APIErrorResponse, "description": "Baseline run was not found"}


def _baseline_metrics(session: Session, baseline: SimulationRun) -> BaselineMetrics:
    baseline_id = int(baseline.id or 0)
    stops = session.exec(select(RouteStop).where(RouteStop.run_id == baseline_id)).all()
    shipped_kg = sum(stop.shipped_kg for stop in stops)
    trucks_used = {stop.truck_id for stop in stops}
    client_trucks: dict[int, set[int]] = {}
    for stop in stops:
        client_trucks.setdefault(stop.client_id, set()).add(stop.truck_id)
    capacities = session.exec(select(Truck).where(Truck.id.in_(trucks_used))).all()
    total_capacity_kg = sum(truck.capacity_kg for truck in capacities)
    load_factor_pct = shipped_kg / total_capacity_kg * 100.0 if total_capacity_kg > 0 else 0.0

    return BaselineMetrics(
        total_tco_rub=baseline.total_tco_rub,
        total_trip_cost_rub=baseline.total_trip_cost_rub,
        total_spoilage_loss_rub=baseline.total_spoilage_loss_rub,
        total_unmet_penalty_rub=baseline.total_unmet_penalty_rub,
        expected_net_profit_rub=baseline.expected_net_profit_rub,
        avg_freshness_pct=baseline.avg_freshness_pct,
        shipped_kg=round(shipped_kg, 3),
        unmet_kg=baseline.total_unmet_kg,
        total_trips=len(trucks_used),
        avg_load_factor_pct=round(min(100.0, max(0.0, load_factor_pct)), 2),
        split_clients=sum(1 for truck_ids in client_trucks.values() if len(truck_ids) > 1),
    )


def _persist_run(
    session: Session,
    outcome: SolverOutcome,
    weather: WeatherSnapshot,
    parent_run_id: int | None,
) -> int:
    run = SimulationRun(
        parent_run_id=parent_run_id,
        weather_mode=weather.mode.value,
        temp_c=weather.temperature_c,
        precip_mm=weather.precipitation_mm,
        total_tco_rub=outcome.metrics.total_tco_rub,
        total_trip_cost_rub=outcome.metrics.total_trip_cost_rub,
        total_spoilage_loss_rub=outcome.metrics.total_spoilage_loss_rub,
        total_unmet_penalty_rub=outcome.metrics.total_unmet_penalty_rub,
        expected_net_profit_rub=outcome.metrics.expected_net_profit_rub,
        avg_freshness_pct=outcome.metrics.avg_freshness_pct,
        total_shipped_kg=outcome.metrics.shipped_kg,
        total_unmet_kg=outcome.metrics.unmet_kg,
    )
    session.add(run)
    # ``flush`` assigns the primary key without committing, so the run and all
    # of its stops land in one transaction: a crash cannot leave a plan without
    # route stops (and the what-if baseline stays consistent).
    session.flush()
    run_id = int(run.id or 0)
    for route in outcome.routes:
        for stop in route.stops:
            session.add(
                RouteStop(
                    run_id=run_id,
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
            )
    session.commit()
    return run_id


async def _solve_current_state(
    session: Session,
    settings: Settings,
) -> tuple[SolverOutcome, WeatherSnapshot]:
    """Re-read ERP and weather from SQLite and build a fresh plan."""

    weather = await get_current_weather(session, settings)
    solver_input = await build_solver_input(session, settings, weather)
    outcome = await solve_async(solver_input, settings.solver_time_limit_sec)
    return outcome, weather


@router.post(
    "/optimize",
    response_model=SolverResponse,
    responses={status.HTTP_404_NOT_FOUND: _NOT_FOUND_RESPONSE},
    summary="Build the baseline plan or recalculate the remaining demand",
)
async def optimize(
    payload: SolverRequest,
    _context: AccessContext,
    session: SessionDependency,
    settings: SettingsDependency,
) -> SolverResponse:
    baseline_id: int | None = None
    baseline: SimulationRun | None = None
    if payload.mode is SolverMode.WHAT_IF:
        baseline_id = payload.baseline_run_id
        baseline = session.get(SimulationRun, baseline_id)
        if baseline is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Simulation run with id {baseline_id} was not found",
            )

    outcome, weather = await _solve_current_state(session, settings)

    comparison: ComparisonDelta | None = None
    if baseline is not None:
        comparison = build_comparison(_baseline_metrics(session, baseline), outcome)

    run_id = _persist_run(session, outcome, weather, parent_run_id=baseline_id)
    return to_solver_response(
        outcome,
        run_id=run_id,
        parent_run_id=baseline_id,
        comparison=comparison,
    )

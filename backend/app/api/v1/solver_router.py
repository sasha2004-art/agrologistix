from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlmodel import Session

from app.core.config import Settings, get_settings
from app.core.database import get_session
from app.core.security import AccessContext
from app.models.run_models import RouteStop, SimulationRun
from app.schemas.enums import SolverMode
from app.schemas.error_schemas import APIErrorResponse
from app.schemas.solver_schemas import SolverRequest, SolverResponse
from app.services.solver_engine import SolverOutcome, solve_async
from app.services.solver_input import build_solver_input
from app.services.solver_mapper import to_solver_response
from app.services.weather_service import get_current_weather

router = APIRouter(prefix="/solver", tags=["solver"])

SessionDependency = Annotated[Session, Depends(get_session)]
SettingsDependency = Annotated[Settings, Depends(get_settings)]

_NOT_IMPLEMENTED_RESPONSE = {
    "model": APIErrorResponse,
    "description": "Scenario mode is not available yet",
}


def _persist_run(session: Session, outcome: SolverOutcome, run: SimulationRun) -> int:
    session.add(run)
    session.commit()
    session.refresh(run)

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


@router.post(
    "/optimize",
    response_model=SolverResponse,
    responses={status.HTTP_501_NOT_IMPLEMENTED: _NOT_IMPLEMENTED_RESPONSE},
    summary="Build the baseline delivery plan and return TCO metrics",
)
async def optimize(
    payload: SolverRequest,
    _context: AccessContext,
    session: SessionDependency,
    settings: SettingsDependency,
) -> SolverResponse:
    if payload.mode is SolverMode.WHAT_IF:
        raise HTTPException(
            status_code=status.HTTP_501_NOT_IMPLEMENTED,
            detail="what_if recalculation is not available yet",
        )

    weather = await get_current_weather(session, settings)
    solver_input = await build_solver_input(session, settings, weather)
    outcome = await solve_async(solver_input, settings.solver_time_limit_sec)

    run = SimulationRun(
        parent_run_id=None,
        weather_mode=weather.mode.value,
        temp_c=weather.temperature_c,
        precip_mm=weather.precipitation_mm,
        total_tco_rub=outcome.metrics.total_tco_rub,
        total_trip_cost_rub=outcome.metrics.total_trip_cost_rub,
        total_spoilage_loss_rub=outcome.metrics.total_spoilage_loss_rub,
        total_unmet_penalty_rub=outcome.metrics.total_unmet_penalty_rub,
        expected_net_profit_rub=outcome.metrics.expected_net_profit_rub,
        avg_freshness_pct=outcome.metrics.avg_freshness_pct,
    )
    run_id = _persist_run(session, outcome, run)

    return to_solver_response(outcome, run_id=run_id)

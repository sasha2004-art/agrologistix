from typing import Annotated

from fastapi import APIRouter, Depends
from sqlmodel import Session

from app.core.config import Settings, get_settings
from app.core.database import get_session
from app.core.security import AccessContext
from app.models.run_models import RouteStop, SimulationRun
from app.schemas.solver_schemas import SolverRequest, SolverResponse
from app.services.solver_engine import SolverOutcome, solve_async
from app.services.solver_input import build_solver_input
from app.services.solver_mapper import to_solver_response
from app.services.weather_service import WeatherSnapshot, get_current_weather

router = APIRouter(prefix="/solver", tags=["solver"])

SessionDependency = Annotated[Session, Depends(get_session)]
SettingsDependency = Annotated[Settings, Depends(get_settings)]


def _persist_run(
    session: Session, outcome: SolverOutcome, weather: WeatherSnapshot, *, account_id: int
) -> int:
    run = SimulationRun(
        account_id=account_id,
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
    # route stops.
    session.flush()
    run_id = int(run.id or 0)
    for route in outcome.routes:
        for stop in route.stops:
            session.add(
                RouteStop(
                    account_id=account_id,
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
                    price_per_kg=stop.price_per_kg,
                    stop_status=stop.stop_status,
                )
            )
    session.commit()
    return run_id


@router.post(
    "/optimize",
    response_model=SolverResponse,
    summary="Rebuild the plan from the current ERP and weather state",
)
async def optimize(
    _payload: SolverRequest,
    context: AccessContext,
    session: SessionDependency,
    settings: SettingsDependency,
) -> SolverResponse:
    weather = await get_current_weather(session, settings, account_id=context.account_id)
    solver_input = await build_solver_input(session, settings, weather, account_id=context.account_id)
    outcome = await solve_async(solver_input, settings.solver_time_limit_sec)
    run_id = _persist_run(session, outcome, weather, account_id=context.account_id)
    return to_solver_response(outcome, run_id=run_id)

"""SQLModel entities for solver runs, route stops and the distance cache."""

from datetime import UTC, datetime

from sqlalchemy import CheckConstraint
from sqlmodel import Field, SQLModel

from app.schemas.enums import StopStatus, WeatherMode


def utc_now() -> datetime:
    return datetime.now(UTC)


class SimulationRun(SQLModel, table=True):
    """Immutable snapshot of one solver calculation."""

    __tablename__ = "simulation_run"

    id: int | None = Field(default=None, primary_key=True)
    parent_run_id: int | None = Field(
        default=None,
        foreign_key="simulation_run.id",
        index=True,
    )
    created_at: datetime = Field(default_factory=utc_now, index=True)
    weather_mode: str = Field(default=WeatherMode.NORMAL.value, max_length=16)
    temp_c: float = Field(default=20.0)
    precip_mm: float = Field(default=0.0, ge=0.0)
    total_tco_rub: float = Field(default=0.0, ge=0.0)
    total_trip_cost_rub: float = Field(default=0.0, ge=0.0)
    total_spoilage_loss_rub: float = Field(default=0.0, ge=0.0)
    total_unmet_penalty_rub: float = Field(default=0.0, ge=0.0)
    expected_net_profit_rub: float = Field(default=0.0)
    avg_freshness_pct: float = Field(default=100.0, ge=0.0, le=100.0)


class RouteStop(SQLModel, table=True):
    """One delivery point inside a solver run."""

    __tablename__ = "route_stop"
    __table_args__ = (
        CheckConstraint("shipped_kg >= 0", name="ck_stop_shipped_non_negative"),
        CheckConstraint("distance_km >= 0", name="ck_stop_distance_non_negative"),
        CheckConstraint("eta_minutes >= 0", name="ck_stop_eta_non_negative"),
        CheckConstraint(
            "expected_freshness >= 0 AND expected_freshness <= 1",
            name="ck_stop_freshness_range",
        ),
        CheckConstraint("trip_leg_cost_rub >= 0", name="ck_stop_cost_non_negative"),
        CheckConstraint(
            "stop_status IN ('planned', 'delivered')",
            name="ck_stop_status",
        ),
    )

    id: int | None = Field(default=None, primary_key=True)
    run_id: int = Field(foreign_key="simulation_run.id", index=True)
    order_id: int | None = Field(default=None, foreign_key="client_order.id", index=True)
    truck_id: int = Field(foreign_key="truck.id", index=True)
    warehouse_id: int = Field(foreign_key="warehouse.id", index=True)
    client_id: int = Field(foreign_key="client.id", index=True)
    product_id: int = Field(foreign_key="product.id", index=True)
    sequence_order: int = Field(ge=1)
    shipped_kg: float = Field(ge=0.0)
    distance_km: float = Field(default=0.0, ge=0.0)
    eta_minutes: float = Field(default=0.0, ge=0.0)
    expected_freshness: float = Field(default=1.0, ge=0.0, le=1.0)
    trip_leg_cost_rub: float = Field(default=0.0, ge=0.0)
    stop_status: str = Field(default=StopStatus.PLANNED.value, max_length=16, index=True)


class RouteCache(SQLModel, table=True):
    """Cached distance and geometry for an ordered coordinate pair."""

    __tablename__ = "route_cache"
    __table_args__ = (
        CheckConstraint("distance_km >= 0", name="ck_route_cache_distance_non_negative"),
        CheckConstraint(
            "base_duration_min >= 0",
            name="ck_route_cache_duration_non_negative",
        ),
    )

    pair_key: str = Field(primary_key=True, max_length=128)
    distance_km: float = Field(ge=0.0)
    base_duration_min: float = Field(ge=0.0)
    geojson_geometry: str | None = Field(default=None)

"""Trip-limit post-check: stops, shift length and freshness floor.

The MILP already caps the number of stops per truck. Travel time and the
freshness decay depend on the stop order, so they are verified after routing:

* stops beyond ``max_stops_per_trip`` are cut off the route tail;
* stops that would arrive after ``max_trip_hours`` are cut off as well;
* stops whose cargo arrives below ``min_stop_freshness`` are cut off too.

Every removed stop is returned to the dispatcher as unmet demand with a
structured warning, so the plan stays feasible and explainable. The improve
stage (stage 3) may place those orders on another trip instead.
"""

from dataclasses import dataclass, replace

from app.schemas.enums import WarningSeverity
from app.services.solver_contract import (
    PlannedRoute,
    PlannedWarning,
    SolverInput,
    SolverOrder,
)

KILOGRAM_PRECISION = 3


@dataclass(frozen=True, slots=True)
class LimitOutcome:
    routes: tuple[PlannedRoute, ...]
    rejected: dict[int, float]
    warnings: tuple[PlannedWarning, ...]


def _cut_route(route: PlannedRoute, keep: int) -> tuple[PlannedRoute, float]:
    """Keep the first ``keep`` stops and return the dropped kilograms."""

    dropped = route.stops[keep:]
    if not dropped:
        return route, 0.0
    kept = route.stops[:keep]
    distance_km = sum(stop.distance_km for stop in kept)
    duration_min = max((stop.eta_minutes for stop in kept), default=0.0)
    cost_rub = sum(stop.trip_leg_cost_rub for stop in kept)
    return (
        replace(
            route,
            stops=tuple(kept),
            total_distance_km=round(distance_km, 3),
            total_duration_min=round(duration_min, 2),
            total_cost_rub=round(cost_rub, 2),
            geometry=route.geometry,
        ),
        round(sum(stop.shipped_kg for stop in dropped), KILOGRAM_PRECISION),
    )


def _route_limit(
    solver_input: SolverInput, route: PlannedRoute
) -> tuple[int, str | None, str | None]:
    """Return how many stops fit and which limits were exceeded."""

    limit = solver_input.max_stops_per_trip
    if len(route.stops) > limit:
        return limit, "stops", f"В рейсе было {len(route.stops)} остановок — оставили {limit}"

    max_minutes = solver_input.max_trip_hours * 60.0
    for position, stop in enumerate(route.stops):
        if stop.eta_minutes > max_minutes:
            return (
                position,
                "hours",
                f"Рейс длиннее {solver_input.max_trip_hours:.0f} ч: поздние точки сняли",
            )
    return len(route.stops), None, None


def _freshness_warnings(
    solver_input: SolverInput,
    route: PlannedRoute,
    orders_by_id: dict[int, SolverOrder],
) -> list[PlannedWarning]:
    """Warn about stops that arrive below the freshness floor."""

    warnings: list[PlannedWarning] = []
    for stop in route.stops:
        if stop.expected_freshness >= solver_input.min_stop_freshness:
            continue
        order = orders_by_id.get(stop.order_id or -1)
        warnings.append(
            PlannedWarning(
                code="freshness_risk",
                message=(
                    # Один знак после запятой: округление до целых давало
                    # «70 % — ниже нормы 70 %» при пороге 0.70.
                    f"Сохранность к доставке {stop.expected_freshness * 100:.1f} % — ниже нормы "
                    f"{solver_input.min_stop_freshness * 100:.0f} %: потери учтены в затратах"
                ),
                severity=WarningSeverity.WARNING.value,
                client_id=order.client_id if order else None,
                order_id=stop.order_id,
            )
        )
    return warnings


def enforce_trip_limits(
    solver_input: SolverInput,
    routes: tuple[PlannedRoute, ...],
    orders_by_id: dict[int, SolverOrder],
    unmet_kg_before: float = 0.0,
) -> LimitOutcome:
    """Drop stops that break trip limits and report them as unmet demand."""

    kept_routes: list[PlannedRoute] = []
    rejected: dict[int, float] = {}
    warnings: list[PlannedWarning] = []

    for route in routes:
        warnings.extend(_freshness_warnings(solver_input, route, orders_by_id))
        keep, _reason_code, message = _route_limit(solver_input, route)
        if keep == len(route.stops):
            kept_routes.append(route)
            continue

        trimmed, dropped_kg = _cut_route(route, keep)
        for stop in route.stops[keep:]:
            if stop.order_id is None:
                continue
            rejected[stop.order_id] = rejected.get(stop.order_id, 0.0) + stop.shipped_kg
        if dropped_kg > 0:
            warnings.append(
                PlannedWarning(
                    code="trip_limit_exceeded",
                    message=message,
                    severity=WarningSeverity.WARNING.value,
                )
            )
        if trimmed.stops:
            kept_routes.append(trimmed)

    # The MILP caps stops itself, so a full truck plus unmet demand means the
    # dispatcher hit the stop limit rather than a capacity limit.
    stops_limit = solver_input.max_stops_per_trip
    at_stop_limit = any(len(route.stops) >= stops_limit for route in kept_routes)
    if unmet_kg_before > KILOGRAM_PRECISION and at_stop_limit:
        warnings.append(
            PlannedWarning(
                code="trip_limit_exceeded",
                message=(
                    f"В один рейс помещается не больше {stops_limit} остановок: "
                    f"часть заказов не влезла в график"
                ),
                severity=WarningSeverity.WARNING.value,
            )
        )

    return LimitOutcome(
        routes=tuple(kept_routes),
        rejected={order_id: round(kg, KILOGRAM_PRECISION) for order_id, kg in rejected.items()},
        warnings=tuple(warnings),
    )

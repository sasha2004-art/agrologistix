"""Thermal degradation math for perishable cargo.

Implements the PRD freshness model:

    E[Freshness] = initial_freshness * exp(-lambda_p * t_actual * k_temp)

where

* ``lambda_p`` is the crop spoilage rate per hour at the reference temperature
  (strawberry 0.08, tomato 0.035, cucumber 0.02) taken from the ``product`` table;
* ``t_actual`` is the travel time in hours:

      t_actual = (distance_km / cruise_speed_kmh) * k_surface * k_rain

  with ``k_surface = 1.35`` for dirt approaches (TRD: dirt roads slow trucks down)
  and ``k_rain = 1 + 0.3 * min(1, precipitation_mm / 10)`` for precipitation;
* ``k_temp`` is the heat multiplier. A reefer keeps it at ``1.0``; without a
  reefer it grows exponentially above ``+22 C``:

      k_temp = exp(0.08 * (temperature_c - 22)) for temperature_c > 22

  The coefficient ``0.08`` is a Q10-like factor: ``exp(0.08 * 10) = 2.23``,
  i.e. spoilage roughly doubles for every ``+10 C`` above the threshold.

The result is always clamped to ``[0, 1]``; money loss follows the PRD term
``shipped_kg * (1 - freshness) * price_per_kg``.

Insulated (isotermic) bodies without a reefer get a higher heat threshold: the
``+6 C`` bonus is the extra inertia of an insulated box, which keeps the cargo
below the degradation point longer. A reefer still wins, because it holds the
factor at ``1.0`` regardless of the outside temperature.
"""

from dataclasses import dataclass
from math import exp

from app.schemas.enums import RoadType

# Dirt road slowdown: an unpaved approach costs about 35% extra time.
DIRT_SURFACE_FACTOR = 1.35
# Precipitation slowdown reaches +30% at 10 mm and stays there.
PRECIPITATION_MAX_FACTOR = 0.3
PRECIPITATION_REFERENCE_MM = 10.0
# Heat threshold from the PRD; below or with a reefer degradation stays at lambda_p.
HEAT_THRESHOLD_C = 22.0
# Insulated body (no reefer) shifts the threshold: "утепление" buys +6 C.
INSULATION_BONUS_C = 6.0
# Q10-like exponential coefficient for heat degradation without a reefer.
HEAT_DECAY_COEFFICIENT = 0.08


@dataclass(frozen=True, slots=True)
class CargoProfile:
    """One shipped crop batch: spoilage rate, starting freshness and price."""

    spoilage_rate: float
    initial_freshness: float = 1.0
    price_per_kg: float = 0.0

    def __post_init__(self) -> None:
        if self.spoilage_rate < 0.0:
            raise ValueError("spoilage_rate must be non-negative")
        if not 0.0 <= self.initial_freshness <= 1.0:
            raise ValueError("initial_freshness must be inside [0, 1]")
        if self.price_per_kg < 0.0:
            raise ValueError("price_per_kg must be non-negative")


@dataclass(frozen=True, slots=True)
class TripConditions:
    """Truck, road and weather conditions of one leg."""

    distance_km: float
    cruise_speed_kmh: float
    road_type: RoadType = RoadType.ASPHALT
    precipitation_mm: float = 0.0
    temperature_c: float = 20.0
    has_reefer: bool = False
    has_insulation: bool = False

    def __post_init__(self) -> None:
        if self.distance_km < 0.0:
            raise ValueError("distance_km must be non-negative")
        if self.cruise_speed_kmh <= 0.0:
            raise ValueError("cruise_speed_kmh must be positive")
        if self.precipitation_mm < 0.0:
            raise ValueError("precipitation_mm must be non-negative")


@dataclass(frozen=True, slots=True)
class TripAssessment:
    """Derived values of one leg: time, heat factor, freshness and money loss."""

    travel_hours: float
    temperature_factor: float
    expected_freshness: float
    spoilage_loss_rub: float


def clamp01(value: float) -> float:
    """Clamp a freshness value into the ``[0, 1]`` range."""

    return min(1.0, max(0.0, value))


def surface_factor(road_type: RoadType) -> float:
    """Time multiplier for the approach road surface."""

    return DIRT_SURFACE_FACTOR if road_type is RoadType.DIRT else 1.0


def precipitation_factor(precipitation_mm: float) -> float:
    """Time multiplier for rain: linear up to +30% at 10 mm/h and above."""

    if precipitation_mm < 0.0:
        raise ValueError("precipitation_mm must be non-negative")
    ratio = min(1.0, precipitation_mm / PRECIPITATION_REFERENCE_MM)
    return 1.0 + PRECIPITATION_MAX_FACTOR * ratio


def heat_limit_c(has_reefer: bool, has_insulation: bool = False) -> float | None:
    """Outside temperature above which heat degradation starts.

    ``None`` means there is no limit: a reefer holds the cargo cold, and an
    insulated body adds ``INSULATION_BONUS_C`` degrees to the plain ``+22 C``
    threshold.
    """

    if has_reefer:
        return None
    return HEAT_THRESHOLD_C + (INSULATION_BONUS_C if has_insulation else 0.0)


def temperature_factor(
    temperature_c: float, has_reefer: bool, has_insulation: bool = False
) -> float:
    """Heat degradation multiplier: ``1.0`` below the limit or with a reefer."""

    limit = heat_limit_c(has_reefer, has_insulation)
    if limit is None or temperature_c <= limit:
        return 1.0
    return exp(HEAT_DECAY_COEFFICIENT * (temperature_c - limit))


def travel_time_hours(trip: TripConditions) -> float:
    """Actual travel time: cruise speed, road surface and precipitation."""

    cruise_hours = trip.distance_km / trip.cruise_speed_kmh
    return (
        cruise_hours * surface_factor(trip.road_type) * precipitation_factor(trip.precipitation_mm)
    )


def freshness_after_hours(
    cargo: CargoProfile,
    travel_hours: float,
    temperature_c: float,
    has_reefer: bool,
    has_insulation: bool = False,
) -> float:
    """PRD decay applied to an already known travel time (used per route leg)."""

    if travel_hours < 0.0:
        raise ValueError("travel_hours must be non-negative")
    decay = exp(
        -cargo.spoilage_rate
        * travel_hours
        * temperature_factor(temperature_c, has_reefer, has_insulation)
    )
    return clamp01(cargo.initial_freshness * decay)


def expected_freshness(cargo: CargoProfile, trip: TripConditions) -> float:
    """PRD freshness of a batch after one leg, clamped to ``[0, 1]``."""

    return freshness_after_hours(
        cargo,
        travel_time_hours(trip),
        trip.temperature_c,
        trip.has_reefer,
        trip.has_insulation,
    )


def spoilage_loss_rub(shipped_kg: float, freshness: float, price_per_kg: float) -> float:
    """Money lost to spoilage: ``kg * (1 - freshness) * price``."""

    if shipped_kg < 0.0:
        raise ValueError("shipped_kg must be non-negative")
    if price_per_kg < 0.0:
        raise ValueError("price_per_kg must be non-negative")
    return shipped_kg * (1.0 - clamp01(freshness)) * price_per_kg


def assess_trip(cargo: CargoProfile, trip: TripConditions, shipped_kg: float) -> TripAssessment:
    """Full leg assessment used by the solver and the API layer."""

    freshness = expected_freshness(cargo, trip)
    return TripAssessment(
        travel_hours=travel_time_hours(trip),
        temperature_factor=temperature_factor(
            trip.temperature_c, trip.has_reefer, trip.has_insulation
        ),
        expected_freshness=freshness,
        spoilage_loss_rub=spoilage_loss_rub(shipped_kg, freshness, cargo.price_per_kg),
    )

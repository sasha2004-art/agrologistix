from collections.abc import Callable
from math import exp

import pytest
from app.schemas.enums import RoadType
from app.services.freshness_math import (
    HEAT_THRESHOLD_C,
    PRECIPITATION_MAX_FACTOR,
    CargoProfile,
    TripConditions,
    assess_trip,
    expected_freshness,
    precipitation_factor,
    spoilage_loss_rub,
    surface_factor,
    temperature_factor,
    travel_time_hours,
)
from app.services.solver_engine import SolverOrder, SolverTruck, truck_can_serve_order

STRAWBERRY_RATE = 0.08
TOMATO_RATE = 0.035
CUCUMBER_RATE = 0.02

NORMAL_TRIP = TripConditions(distance_km=100.0, cruise_speed_kmh=60.0)
NORMAL_CARGO = CargoProfile(spoilage_rate=STRAWBERRY_RATE, price_per_kg=320.0)


def test_normal_trip_keeps_most_freshness() -> None:
    freshness = expected_freshness(NORMAL_CARGO, NORMAL_TRIP)

    assert travel_time_hours(NORMAL_TRIP) == pytest.approx(1.6666667, abs=1e-6)
    assert freshness == pytest.approx(0.8751733, abs=1e-6)


def test_heat_without_reefer_accelerates_spoilage() -> None:
    heat = TripConditions(
        distance_km=100.0,
        cruise_speed_kmh=60.0,
        temperature_c=35.0,
        has_reefer=False,
    )
    freshness = expected_freshness(NORMAL_CARGO, heat)

    assert freshness == pytest.approx(0.6857591, abs=1e-6)
    assert freshness < expected_freshness(NORMAL_CARGO, NORMAL_TRIP)


def test_reefer_neutralizes_heat() -> None:
    heat_with_reefer = TripConditions(
        distance_km=100.0,
        cruise_speed_kmh=60.0,
        temperature_c=35.0,
        has_reefer=True,
    )

    assert expected_freshness(NORMAL_CARGO, heat_with_reefer) == pytest.approx(
        expected_freshness(NORMAL_CARGO, NORMAL_TRIP),
        abs=1e-12,
    )


def test_heat_factor_is_exponential_q10_like() -> None:
    thirty = temperature_factor(30.0, has_reefer=False)
    thirty_two = temperature_factor(32.0, has_reefer=False)

    assert thirty == pytest.approx(exp(0.08 * 8.0), abs=1e-12)
    assert thirty_two / temperature_factor(HEAT_THRESHOLD_C, has_reefer=False) == pytest.approx(
        exp(0.08 * 10.0), abs=1e-12
    )
    assert exp(0.08 * 10.0) == pytest.approx(2.2255, abs=1e-3)


def test_temperature_factor_threshold_and_reefer() -> None:
    assert temperature_factor(20.0, has_reefer=False) == 1.0
    assert temperature_factor(HEAT_THRESHOLD_C, has_reefer=False) == 1.0
    assert temperature_factor(22.5, has_reefer=False) == pytest.approx(1.0408108, abs=1e-6)
    assert temperature_factor(45.0, has_reefer=True) == 1.0


def test_dirt_road_multiplies_travel_time() -> None:
    dirt = TripConditions(distance_km=100.0, cruise_speed_kmh=60.0, road_type=RoadType.DIRT)

    assert surface_factor(RoadType.DIRT) == 1.35
    assert surface_factor(RoadType.ASPHALT) == 1.0
    assert travel_time_hours(dirt) == pytest.approx(2.25, abs=1e-9)
    assert expected_freshness(NORMAL_CARGO, dirt) == pytest.approx(0.8352702, abs=1e-6)


def test_precipitation_slowdown_is_capped() -> None:
    assert precipitation_factor(0.0) == 1.0
    assert precipitation_factor(5.0) == pytest.approx(1.15, abs=1e-12)
    assert precipitation_factor(10.0) == pytest.approx(1.0 + PRECIPITATION_MAX_FACTOR, abs=1e-12)
    assert precipitation_factor(50.0) == pytest.approx(1.0 + PRECIPITATION_MAX_FACTOR, abs=1e-12)

    rain = TripConditions(distance_km=100.0, cruise_speed_kmh=60.0, precipitation_mm=12.0)
    assert travel_time_hours(rain) == pytest.approx(2.1666667, abs=1e-6)
    assert expected_freshness(NORMAL_CARGO, rain) == pytest.approx(0.8408573, abs=1e-6)


def test_combined_stress_scenario() -> None:
    stress = TripConditions(
        distance_km=100.0,
        cruise_speed_kmh=60.0,
        road_type=RoadType.DIRT,
        precipitation_mm=12.0,
        temperature_c=35.0,
        has_reefer=False,
    )

    assert travel_time_hours(stress) == pytest.approx(2.925, abs=1e-9)
    assert expected_freshness(NORMAL_CARGO, stress) == pytest.approx(0.5157997, abs=1e-6)


def test_spoilage_rate_order_matches_crops() -> None:
    strawberry = expected_freshness(CargoProfile(STRAWBERRY_RATE), NORMAL_TRIP)
    tomato = expected_freshness(CargoProfile(TOMATO_RATE), NORMAL_TRIP)
    cucumber = expected_freshness(CargoProfile(CUCUMBER_RATE), NORMAL_TRIP)

    assert strawberry < tomato < cucumber
    assert tomato == pytest.approx(0.9433354, abs=1e-6)
    assert cucumber == pytest.approx(0.9672161, abs=1e-6)


def test_initial_freshness_scales_the_result() -> None:
    freshness = expected_freshness(
        CargoProfile(spoilage_rate=STRAWBERRY_RATE, initial_freshness=0.8),
        NORMAL_TRIP,
    )

    assert freshness == pytest.approx(0.7001387, abs=1e-6)


def test_freshness_is_always_clamped_into_unit_range() -> None:
    too_long = TripConditions(distance_km=100_000.0, cruise_speed_kmh=10.0, temperature_c=45.0)
    no_spoilage = CargoProfile(spoilage_rate=0.0)

    assert expected_freshness(NORMAL_CARGO, too_long) == 0.0
    assert expected_freshness(no_spoilage, NORMAL_TRIP) == 1.0


def test_spoilage_loss_follows_prd_formula() -> None:
    assert spoilage_loss_rub(1000.0, 0.9, 200.0) == pytest.approx(20_000.0)
    assert spoilage_loss_rub(1000.0, 1.0, 200.0) == 0.0
    assert spoilage_loss_rub(0.0, 0.5, 200.0) == 0.0


def test_assess_trip_reports_all_components() -> None:
    assessment = assess_trip(NORMAL_CARGO, NORMAL_TRIP, shipped_kg=1000.0)

    assert assessment.travel_hours == pytest.approx(1.6666667, abs=1e-6)
    assert assessment.temperature_factor == 1.0
    assert assessment.expected_freshness == pytest.approx(0.8751733, abs=1e-6)
    assert assessment.spoilage_loss_rub == pytest.approx(39_944.54, abs=0.01)


@pytest.mark.parametrize(
    "factory",
    [
        lambda: CargoProfile(spoilage_rate=-0.01),
        lambda: CargoProfile(spoilage_rate=0.08, initial_freshness=1.2),
        lambda: CargoProfile(spoilage_rate=0.08, price_per_kg=-1.0),
        lambda: TripConditions(distance_km=-1.0, cruise_speed_kmh=60.0),
        lambda: TripConditions(distance_km=10.0, cruise_speed_kmh=0.0),
        lambda: TripConditions(distance_km=10.0, cruise_speed_kmh=60.0, precipitation_mm=-1.0),
    ],
)
def test_invalid_inputs_are_rejected(factory: Callable[[], object]) -> None:
    with pytest.raises(ValueError):
        factory()


def test_higher_cruise_speed_keeps_cargo_fresher() -> None:
    fast = TripConditions(distance_km=100.0, cruise_speed_kmh=120.0)
    slow = TripConditions(distance_km=100.0, cruise_speed_kmh=30.0)

    assert travel_time_hours(fast) < travel_time_hours(slow)
    assert expected_freshness(NORMAL_CARGO, fast) > expected_freshness(NORMAL_CARGO, slow)


def test_unreachable_dirt_scenario_requires_offroad_truck() -> None:
    euro_truck = SolverTruck(
        truck_id=1,
        name="Volvo FH16 Еврофура",
        warehouse_id=1,
        capacity_kg=20_000.0,
        cruise_speed_kmh=75.0,
        cost_per_km_rub=58.0,
        fixed_trip_cost_rub=8_500.0,
        has_reefer=True,
        can_use_dirt=False,
    )
    offroad_truck = SolverTruck(
        truck_id=2,
        name="ГАЗон NEXT Вездеход",
        warehouse_id=1,
        capacity_kg=6_000.0,
        cruise_speed_kmh=62.0,
        cost_per_km_rub=32.0,
        fixed_trip_cost_rub=3_800.0,
        has_reefer=True,
        can_use_dirt=True,
    )
    dirt_order = SolverOrder(
        order_id=1,
        client_id=3,
        product_id=1,
        requested_kg=800.0,
        price_per_kg=300.0,
        penalty_per_kg=150.0,
        road_type=RoadType.DIRT,
        latitude=55.2075,
        longitude=36.4850,
    )
    asphalt_order = SolverOrder(
        order_id=2,
        client_id=1,
        product_id=1,
        requested_kg=1500.0,
        price_per_kg=320.0,
        penalty_per_kg=120.0,
        road_type=RoadType.ASPHALT,
        latitude=54.5138,
        longitude=36.2612,
    )

    assert truck_can_serve_order(euro_truck, dirt_order) is False
    assert truck_can_serve_order(offroad_truck, dirt_order) is True
    assert truck_can_serve_order(euro_truck, asphalt_order) is True

"""End-to-end math scenarios built on the real Kaluga seed dataset."""

import pytest
from app.models.erp_models import Client, Product, Truck, Warehouse
from app.schemas.enums import RoadType
from app.services.distance_matrix import Coordinate, fallback_leg
from app.services.freshness_math import CargoProfile, TripConditions, expected_freshness
from app.services.seed_kaluga import seed_database
from sqlmodel import Session, select

OBININSK = Coordinate(lat=55.0968, lon=36.6103)


def _product(session: Session, code: str) -> Product:
    product = session.exec(select(Product).where(Product.code == code)).one()
    return product


def _client(session: Session, name: str) -> Client:
    client = session.exec(select(Client).where(Client.name == name)).one()
    return client


def _truck(session: Session, plate: str) -> Truck:
    truck = session.exec(select(Truck).where(Truck.plate_number == plate)).one()
    return truck


def _warehouse(session: Session, name: str) -> Warehouse:
    warehouse = session.exec(select(Warehouse).where(Warehouse.name == name)).one()
    return warehouse


def _distance_km(session: Session, client: Client) -> float:
    warehouse = _warehouse(session, "Хаб Обнинск")
    leg = fallback_leg(
        Coordinate(lat=warehouse.lat, lon=warehouse.lon),
        Coordinate(lat=client.lat, lon=client.lon),
    )
    return leg.distance_km


def test_normal_reefer_trip_keeps_strawberry_fresh(session: Session) -> None:
    seed_database(session)
    strawberry = _product(session, "strawberry")
    kaluga = _client(session, "ВкусВилл")
    volvo = _truck(session, "А001АА40")

    trip = TripConditions(
        distance_km=_distance_km(session, kaluga),
        cruise_speed_kmh=volvo.cruise_speed_kmh,
        road_type=RoadType(kaluga.road_type),
        temperature_c=20.0,
        has_reefer=volvo.has_reefer,
    )
    cargo = CargoProfile(spoilage_rate=strawberry.base_spoilage_rate, price_per_kg=320.0)

    assert kaluga.road_type == "asphalt"
    assert expected_freshness(cargo, trip) > 0.85


def test_heatwave_without_reefer_spoils_strawberry(session: Session) -> None:
    seed_database(session)
    strawberry = _product(session, "strawberry")
    kaluga = _client(session, "ВкусВилл")
    kamaz = _truck(session, "С303СС40")
    volvo = _truck(session, "А001АА40")

    distance_km = _distance_km(session, kaluga)
    cargo = CargoProfile(spoilage_rate=strawberry.base_spoilage_rate)

    unrefrigerated = TripConditions(
        distance_km=distance_km,
        cruise_speed_kmh=kamaz.cruise_speed_kmh,
        temperature_c=35.0,
        has_reefer=kamaz.has_reefer,
    )
    refrigerated = TripConditions(
        distance_km=distance_km,
        cruise_speed_kmh=volvo.cruise_speed_kmh,
        temperature_c=35.0,
        has_reefer=volvo.has_reefer,
    )

    assert kamaz.has_reefer is False
    assert volvo.has_reefer is True
    assert expected_freshness(cargo, unrefrigerated) < 0.8
    assert expected_freshness(cargo, unrefrigerated) < expected_freshness(cargo, refrigerated)


def test_dirt_approach_is_slower_than_asphalt(session: Session) -> None:
    seed_database(session)
    strawberry = _product(session, "strawberry")
    borovsk = _client(session, "Кооператив Боровск")
    gazelle = _truck(session, "В202ВВ40")

    distance_km = _distance_km(session, borovsk)

    asphalt = TripConditions(
        distance_km=distance_km,
        cruise_speed_kmh=gazelle.cruise_speed_kmh,
        road_type=RoadType.ASPHALT,
    )
    dirt = TripConditions(
        distance_km=distance_km,
        cruise_speed_kmh=gazelle.cruise_speed_kmh,
        road_type=RoadType.DIRT,
    )
    cargo = CargoProfile(spoilage_rate=strawberry.base_spoilage_rate)

    assert borovsk.road_type == "dirt"
    assert expected_freshness(cargo, dirt) < expected_freshness(cargo, asphalt)
    assert expected_freshness(cargo, dirt) == pytest.approx(
        expected_freshness(cargo, asphalt) ** 1.35,
        rel=1e-9,
    )


def test_obninsk_warehouse_is_the_loading_origin(session: Session) -> None:
    seed_database(session)
    warehouse = _warehouse(session, "Хаб Обнинск")
    tarusa = _client(session, "Эко-база")

    assert warehouse.is_active is True
    assert OBININSK.lat == pytest.approx(warehouse.lat, abs=1e-9)
    assert _distance_km(session, tarusa) > 0.0

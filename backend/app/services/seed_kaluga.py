"""Idempotent seed data for the Kaluga region demo scenario."""

from dataclasses import dataclass

from sqlalchemy import func
from sqlmodel import Session, delete, select

from app.models.erp_models import (
    Client,
    ClientOrder,
    Product,
    Truck,
    Warehouse,
    WarehouseStock,
)
from app.models.run_models import RouteCache, RouteStop, SimulationRun
from app.schemas.enums import DeliveryStatus, RoadType, TruckStatus

WAREHOUSE_SEED: tuple[dict[str, object], ...] = (
    {
        "name": "Хаб Обнинск-Северный",
        "lat": 55.0968,
        "lon": 36.6103,
        "address": "г. Обнинск, ул. Северная, 1",
    },
    {
        "name": "Склад Детчино-Агро",
        "lat": 54.8083,
        "lon": 36.2333,
        "address": "с. Детчино, ул. Агропромышленная, 7",
    },
)

PRODUCT_SEED: tuple[dict[str, object], ...] = (
    {
        "code": "strawberry",
        "name": "Клубника садовая",
        "base_spoilage_rate": 0.08,
        "optimal_temp_c": 4.0,
        "base_cost_rub": 180.0,
    },
    {
        "code": "tomato",
        "name": "Томаты тепличные",
        "base_spoilage_rate": 0.035,
        "optimal_temp_c": 10.0,
        "base_cost_rub": 95.0,
    },
    {
        "code": "cucumber",
        "name": "Огурцы короткоплодные",
        "base_spoilage_rate": 0.02,
        "optimal_temp_c": 10.0,
        "base_cost_rub": 70.0,
    },
)

STOCK_SEED: tuple[tuple[str, str, float], ...] = (
    ("Хаб Обнинск-Северный", "strawberry", 4200.0),
    ("Хаб Обнинск-Северный", "tomato", 8600.0),
    ("Хаб Обнинск-Северный", "cucumber", 5400.0),
    ("Склад Детчино-Агро", "strawberry", 2600.0),
    ("Склад Детчино-Агро", "tomato", 5200.0),
    ("Склад Детчино-Агро", "cucumber", 3800.0),
)

CLIENT_SEED: tuple[dict[str, object], ...] = (
    {
        "name": "РЦ «ВкусВилл» Калуга",
        "lat": 54.5138,
        "lon": 36.2612,
        "road_type": RoadType.ASPHALT.value,
        "address": "г. Калуга, ул. Московская, 300",
    },
    {
        "name": "Агро-Рынок Малоярославец",
        "lat": 55.0147,
        "lon": 36.4719,
        "road_type": RoadType.ASPHALT.value,
        "address": "г. Малоярославец, ул. Плеханова, 12",
    },
    {
        "name": "Фермерский кооператив Боровск",
        "lat": 55.2075,
        "lon": 36.4850,
        "road_type": RoadType.DIRT.value,
        "address": "г. Боровск, ул. Ленина, 44",
    },
    {
        "name": "Сеть «Пятёрочка» Балабаново",
        "lat": 55.1797,
        "lon": 36.6597,
        "road_type": RoadType.ASPHALT.value,
        "address": "г. Балабаново, ул. Гагарина, 8",
    },
    {
        "name": "Эко-база Таруса",
        "lat": 54.7200,
        "lon": 37.1800,
        "road_type": RoadType.DIRT.value,
        "address": "г. Таруса, ул. Окская, 3",
    },
)

ORDER_SEED: tuple[tuple[str, str, float, float, float], ...] = (
    ("РЦ «ВкусВилл» Калуга", "strawberry", 1500.0, 320.0, 120.0),
    ("РЦ «ВкусВилл» Калуга", "tomato", 2000.0, 160.0, 80.0),
    ("Агро-Рынок Малоярославец", "tomato", 1200.0, 150.0, 70.0),
    ("Агро-Рынок Малоярославец", "cucumber", 900.0, 110.0, 50.0),
    ("Фермерский кооператив Боровск", "strawberry", 800.0, 300.0, 150.0),
    ("Фермерский кооператив Боровск", "cucumber", 1100.0, 105.0, 45.0),
    ("Сеть «Пятёрочка» Балабаново", "tomato", 1800.0, 155.0, 75.0),
    ("Сеть «Пятёрочка» Балабаново", "strawberry", 700.0, 310.0, 140.0),
    ("Эко-база Таруса", "cucumber", 1000.0, 115.0, 55.0),
)

TRUCK_SEED: tuple[dict[str, object], ...] = (
    {
        "name": "Volvo FH16 Еврофура Реф",
        "plate_number": "А001АА40",
        "warehouse": "Хаб Обнинск-Северный",
        "capacity_kg": 20000.0,
        "cruise_speed_kmh": 75.0,
        "cost_per_km_rub": 58.0,
        "fixed_trip_cost_rub": 8500.0,
        "has_reefer": True,
        "can_use_dirt": False,
    },
    {
        "name": "ГАЗон NEXT Реф-Вездеход",
        "plate_number": "В202ВВ40",
        "warehouse": "Хаб Обнинск-Северный",
        "capacity_kg": 6000.0,
        "cruise_speed_kmh": 62.0,
        "cost_per_km_rub": 32.0,
        "fixed_trip_cost_rub": 3800.0,
        "has_reefer": True,
        "can_use_dirt": True,
    },
    {
        "name": "КАМАЗ Компас Тент",
        "plate_number": "С303СС40",
        "warehouse": "Склад Детчино-Агро",
        "capacity_kg": 10000.0,
        "cruise_speed_kmh": 70.0,
        "cost_per_km_rub": 40.0,
        "fixed_trip_cost_rub": 4600.0,
        "has_reefer": False,
        "can_use_dirt": True,
    },
)


@dataclass(frozen=True, slots=True)
class SeedSummary:
    warehouses: int
    products: int
    stocks: int
    clients: int
    orders: int
    trucks: int
    seeded: bool


def collect_summary(session: Session, *, seeded: bool = False) -> SeedSummary:
    def count(model: type) -> int:
        statement = select(func.count()).select_from(model)
        return int(session.exec(statement).one())

    return SeedSummary(
        warehouses=count(Warehouse),
        products=count(Product),
        stocks=count(WarehouseStock),
        clients=count(Client),
        orders=count(ClientOrder),
        trucks=count(Truck),
        seeded=seeded,
    )


def _insert_reference_data(session: Session) -> None:
    warehouses = {str(item["name"]): Warehouse(**item) for item in WAREHOUSE_SEED}
    session.add_all(list(warehouses.values()))
    session.flush()

    products = {str(item["code"]): Product(**item) for item in PRODUCT_SEED}
    session.add_all(list(products.values()))
    session.flush()

    for warehouse_name, product_code, available_kg in STOCK_SEED:
        session.add(
            WarehouseStock(
                warehouse_id=int(warehouses[warehouse_name].id or 0),
                product_id=int(products[product_code].id or 0),
                available_kg=available_kg,
                initial_freshness=1.0,
            )
        )

    clients = {str(item["name"]): Client(**item) for item in CLIENT_SEED}
    session.add_all(list(clients.values()))
    session.flush()

    for client_name, product_code, requested_kg, price, penalty in ORDER_SEED:
        session.add(
            ClientOrder(
                client_id=int(clients[client_name].id or 0),
                product_id=int(products[product_code].id or 0),
                requested_kg=requested_kg,
                purchase_price_rub=price,
                unmet_penalty_rub=penalty,
                delivery_status=DeliveryStatus.PENDING.value,
            )
        )

    for item in TRUCK_SEED:
        payload = dict(item)
        warehouse_name = str(payload.pop("warehouse"))
        session.add(
            Truck(
                warehouse_id=int(warehouses[warehouse_name].id or 0),
                status=TruckStatus.ACTIVE.value,
                **payload,  # type: ignore[arg-type]
            )
        )


def seed_database(session: Session) -> SeedSummary:
    """Populate the Kaluga demo data once, leaving existing state untouched."""

    if session.exec(select(Warehouse.id).limit(1)).first() is not None:
        return collect_summary(session)

    _insert_reference_data(session)
    session.commit()
    return collect_summary(session, seeded=True)


def reset_demo_database(session: Session) -> SeedSummary:
    """Drop every persisted record and rebuild the demo state from scratch."""

    for model in (RouteStop, SimulationRun, RouteCache):
        session.exec(delete(model))
    for model in (ClientOrder, WarehouseStock, Truck, Client, Product, Warehouse):
        session.exec(delete(model))
    session.commit()

    _insert_reference_data(session)
    session.commit()
    return collect_summary(session, seeded=True)

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
from app.models.run_models import (
    DeliveredOrderStock,
    FixedAssignment,
    RouteCache,
    RouteStop,
    SimulationRun,
    WeatherOverrideState,
)
from app.schemas.enums import DeliveryStatus, RoadType, TruckStatus

WAREHOUSE_SEED: tuple[dict[str, object], ...] = (
    {
        "name": "Хаб Обнинск",
        "lat": 55.0968,
        "lon": 36.6103,
        "address": "г. Обнинск, ул. Северная, 1",
    },
    {
        "name": "Склад Детчино",
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
        "base_cost_rub": 90.0,
    },
    {
        "code": "tomato",
        "name": "Томаты тепличные",
        "base_spoilage_rate": 0.035,
        "optimal_temp_c": 10.0,
        "base_cost_rub": 47.5,
    },
    {
        "code": "cucumber",
        "name": "Огурцы короткоплодные",
        "base_spoilage_rate": 0.02,
        "optimal_temp_c": 10.0,
        "base_cost_rub": 35.0,
    },
)

# Warehouse stock batches: (warehouse, product, available_kg, initial_freshness).
# Volumes match hub-scale batches (tens of tonnes per crop), not shop orders.
# Freshness mirrors a realistic cold chain: the Obninsk hub ships recently
# harvested lots (0.90-0.97), while the Detchino site keeps older batches, so
# strawberries and cucumbers there are noticeably closer to spoiling.
STOCK_SEED: tuple[tuple[str, str, float, float], ...] = (
    ("Хаб Обнинск", "strawberry", 4500.0, 0.97),
    ("Хаб Обнинск", "tomato", 11000.0, 0.93),
    ("Хаб Обнинск", "cucumber", 7000.0, 0.90),
    ("Склад Детчино", "strawberry", 2500.0, 0.82),
    ("Склад Детчино", "tomato", 6000.0, 0.95),
    ("Склад Детчино", "cucumber", 3500.0, 0.78),
)

CLIENT_SEED: tuple[dict[str, object], ...] = (
    {
        "name": "ВкусВилл",
        "lat": 54.5138,
        "lon": 36.2612,
        "road_type": RoadType.ASPHALT.value,
        "address": "г. Калуга, ул. Московская, 300",
    },
    {
        "name": "Агро-Рынок",
        "lat": 55.0147,
        "lon": 36.4719,
        "road_type": RoadType.ASPHALT.value,
        "address": "г. Малоярославец, ул. Плеханова, 12",
    },
    {
        "name": "Кооператив Боровск",
        "lat": 55.2075,
        "lon": 36.4850,
        "road_type": RoadType.DIRT.value,
        "address": "г. Боровск, ул. Ленина, 44",
    },
    {
        "name": "Пятёрочка",
        "lat": 55.1797,
        "lon": 36.6597,
        "road_type": RoadType.ASPHALT.value,
        "address": "г. Балабаново, ул. Гагарина, 8",
    },
    {
        "name": "Эко-база",
        "lat": 54.7200,
        "lon": 37.1800,
        "road_type": RoadType.DIRT.value,
        "address": "г. Таруса, ул. Окская, 3",
    },
    {
        "name": "Ферма Заречье",
        "lat": 54.9500,
        "lon": 36.4000,
        "road_type": RoadType.ASPHALT.value,
        "address": "Калужская обл., д. Заречье",
    },
    {
        "name": "Ресторан Калуга",
        "lat": 54.5500,
        "lon": 36.3200,
        "road_type": RoadType.ASPHALT.value,
        "address": "г. Калуга, ул. Театральная, 12",
    },
    {
        "name": "Садовая база",
        "lat": 55.2600,
        "lon": 36.7000,
        "road_type": RoadType.DIRT.value,
        "address": "Боровский р-н, д. Ворсино",
    },
)

# Five orders cover five clients; the other clients remain visible on the map
# without adding demand or external routing requests to the calculation.
ORDER_SEED: tuple[tuple[int, str, str, float, float, float], ...] = (
    (1, "ВкусВилл", "strawberry", 400.0, 160.0, 60.0),
    (2, "Агро-Рынок", "tomato", 600.0, 75.0, 35.0),
    (5, "Кооператив Боровск", "strawberry", 150.0, 150.0, 75.0),
    (6, "Кооператив Боровск", "cucumber", 250.0, 52.5, 22.5),
    (9, "Эко-база", "cucumber", 300.0, 57.5, 27.5),
)

TRUCK_SEED: tuple[dict[str, object], ...] = (
    {
        "name": "Volvo FH16",
        "plate_number": "А001АА40",
        "warehouse": "Хаб Обнинск",
        "capacity_kg": 10000.0,
        "cruise_speed_kmh": 75.0,
        "cost_per_km_rub": 29.0,
        "fixed_trip_cost_rub": 4250.0,
        "has_reefer": True,
        "has_insulation": False,
        "can_use_dirt": False,
    },
    {
        "name": "ГАЗон NEXT",
        "plate_number": "В202ВВ40",
        "warehouse": "Хаб Обнинск",
        "capacity_kg": 3000.0,
        "cruise_speed_kmh": 62.0,
        "cost_per_km_rub": 16.0,
        "fixed_trip_cost_rub": 1900.0,
        "has_reefer": True,
        "has_insulation": False,
        "can_use_dirt": True,
    },
    {
        "name": "КАМАЗ Компас",
        "plate_number": "С303СС40",
        "warehouse": "Склад Детчино",
        "capacity_kg": 5000.0,
        "cruise_speed_kmh": 70.0,
        "cost_per_km_rub": 20.0,
        "fixed_trip_cost_rub": 2300.0,
        "has_reefer": False,
        # Изотермический кузов без холодильной установки: в жару порча
        # начинается на +6 °C позже, чем у обычного тента.
        "has_insulation": True,
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
    session.add(WeatherOverrideState())
    warehouses = {str(item["name"]): Warehouse(**item) for item in WAREHOUSE_SEED}
    session.add_all(list(warehouses.values()))
    session.flush()

    products = {str(item["code"]): Product(**item) for item in PRODUCT_SEED}
    session.add_all(list(products.values()))
    session.flush()

    for warehouse_name, product_code, available_kg, initial_freshness in STOCK_SEED:
        session.add(
            WarehouseStock(
                warehouse_id=int(warehouses[warehouse_name].id or 0),
                product_id=int(products[product_code].id or 0),
                available_kg=available_kg,
                initial_freshness=initial_freshness,
            )
        )

    clients = {str(item["name"]): Client(**item) for item in CLIENT_SEED}
    session.add_all(list(clients.values()))
    session.flush()

    for order_id, client_name, product_code, requested_kg, price, penalty in ORDER_SEED:
        session.add(
            ClientOrder(
                id=order_id,
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

    for model in (
        RouteStop,
        SimulationRun,
        FixedAssignment,
        RouteCache,
        WeatherOverrideState,
        DeliveredOrderStock,
    ):
        session.exec(delete(model))
    for model in (ClientOrder, WarehouseStock, Truck, Client, Product, Warehouse):
        session.exec(delete(model))
    session.commit()

    _insert_reference_data(session)
    session.commit()
    return collect_summary(session, seeded=True)

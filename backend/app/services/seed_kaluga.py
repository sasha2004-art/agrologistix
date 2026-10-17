"""Idempotent multi-account seed data for the Kaluga region demo scenario."""

from dataclasses import dataclass

from sqlalchemy import func
from sqlmodel import Session, delete, select

from app.models.erp_models import (
    Account,
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
from app.schemas.enums import DeliveryStatus, RoadType, TruckStatus, WeatherMode

ACCOUNT_SEED: tuple[tuple[int, str, str], ...] = (
    (1, "Обнинск-Alpha", "202601"),
    (2, "Обнинск-Bravo", "310247"),
    (3, "Обнинск-Charlie", "428915"),
    (4, "Обнинск-Delta", "537084"),
    (5, "Обнинск-Echo", "649173"),
    (6, "Обнинск-Foxtrot", "758302"),
)

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


def _count(session: Session, model: type, account_id: int) -> int:
    return int(
        session.exec(
            select(func.count())
            .select_from(model)
            .where(model.account_id == account_id)
        ).one()
    )


def collect_summary(session: Session, *, account_id: int, seeded: bool = False) -> SeedSummary:
    return SeedSummary(
        warehouses=_count(session, Warehouse, account_id),
        products=_count(session, Product, account_id),
        stocks=_count(session, WarehouseStock, account_id),
        clients=_count(session, Client, account_id),
        orders=_count(session, ClientOrder, account_id),
        trucks=_count(session, Truck, account_id),
        seeded=seeded,
    )


def _variant(account_id: int) -> float:
    return 1.0 + (account_id - 1) * 0.04


def _insert_reference_data(session: Session, account: Account) -> None:
    account_id = int(account.id or 0)
    variant = _variant(account_id)
    suffix = f" [{account.name}]"
    plate_suffix = f"{account_id:02d}"

    session.add(WeatherOverrideState(account_id=account_id, mode=WeatherMode.NORMAL.value))
    warehouses = {
        str(item["name"]): Warehouse(
            account_id=account_id,
            name=f"{item['name']}{suffix}",
            lat=float(item["lat"]) + account_id * 0.002,
            lon=float(item["lon"]) + account_id * 0.002,
            address=str(item["address"]),
        )
        for item in WAREHOUSE_SEED
    }
    session.add_all(list(warehouses.values()))
    session.flush()

    products = {
        str(item["code"]): Product(
            account_id=account_id,
            code=f"{item['code']}_{account_id}",
            name=f"{item['name']} {account.name}",
            base_spoilage_rate=float(item["base_spoilage_rate"]),
            optimal_temp_c=float(item["optimal_temp_c"]),
            base_cost_rub=round(float(item["base_cost_rub"]) * variant, 2),
        )
        for item in PRODUCT_SEED
    }
    session.add_all(list(products.values()))
    session.flush()

    for warehouse_name, product_code, available_kg, initial_freshness in STOCK_SEED:
        session.add(
            WarehouseStock(
                account_id=account_id,
                warehouse_id=int(warehouses[warehouse_name].id or 0),
                product_id=int(products[product_code].id or 0),
                available_kg=round(available_kg * variant, 2),
                initial_freshness=max(0.5, min(1.0, initial_freshness - (account_id - 1) * 0.01)),
            )
        )

    clients = {
        str(item["name"]): Client(
            account_id=account_id,
            name=f"{item['name']}{suffix}",
            lat=float(item["lat"]) + account_id * 0.0015,
            lon=float(item["lon"]) + account_id * 0.0015,
            road_type=str(item["road_type"]),
            address=str(item["address"]),
        )
        for item in CLIENT_SEED
    }
    session.add_all(list(clients.values()))
    session.flush()

    for _, client_name, product_code, requested_kg, price, penalty in ORDER_SEED:
        session.add(
            ClientOrder(
                account_id=account_id,
                client_id=int(clients[client_name].id or 0),
                product_id=int(products[product_code].id or 0),
                requested_kg=round(requested_kg * variant, 2),
                purchase_price_rub=round(price * variant, 2),
                unmet_penalty_rub=round(penalty * variant, 2),
                delivery_status=DeliveryStatus.PENDING.value,
            )
        )

    for item in TRUCK_SEED:
        payload = dict(item)
        warehouse_name = str(payload.pop("warehouse"))
        session.add(
            Truck(
                account_id=account_id,
                warehouse_id=int(warehouses[warehouse_name].id or 0),
                status=TruckStatus.ACTIVE.value,
                name=f"{payload['name']} {account.name}",
                plate_number=f"{payload['plate_number']}{plate_suffix}",
                capacity_kg=round(float(payload["capacity_kg"]) * variant, 2),
                cruise_speed_kmh=float(payload["cruise_speed_kmh"]),
                cost_per_km_rub=round(float(payload["cost_per_km_rub"]) * variant, 2),
                fixed_trip_cost_rub=round(float(payload["fixed_trip_cost_rub"]) * variant, 2),
                has_reefer=bool(payload["has_reefer"]),
                has_insulation=bool(payload["has_insulation"]),
                can_use_dirt=bool(payload["can_use_dirt"]),
            )
        )


def _ensure_accounts(session: Session) -> dict[int, Account]:
    accounts = {int(account.id or 0): account for account in session.exec(select(Account)).all()}
    changed = False
    for account_id, name, access_code in ACCOUNT_SEED:
        account = accounts.get(account_id)
        if account is None:
            account = Account(id=account_id, name=name, access_code=access_code)
            session.add(account)
            changed = True
            accounts[account_id] = account
        else:
            if account.name != name or account.access_code != access_code:
                account.name = name
                account.access_code = access_code
                session.add(account)
                changed = True
    if changed:
        session.commit()
        accounts = {
            int(account.id or 0): account for account in session.exec(select(Account)).all()
        }
    return accounts


def seed_database(session: Session) -> SeedSummary:
    """Populate six isolated demo accounts once, leaving existing state untouched."""

    accounts = _ensure_accounts(session)
    for account_id, *_ in ACCOUNT_SEED:
        if session.exec(
            select(Warehouse.id).where(Warehouse.account_id == account_id).limit(1)
        ).first():
            continue
        account = accounts[account_id]
        _insert_reference_data(session, account)
    session.commit()
    return collect_summary(session, account_id=1)


def reset_demo_database(session: Session, *, account_id: int) -> SeedSummary:
    """Drop and rebuild demo state only for the selected account."""

    for model in (
        RouteStop,
        SimulationRun,
        FixedAssignment,
        RouteCache,
        WeatherOverrideState,
        DeliveredOrderStock,
    ):
        session.exec(delete(model).where(model.account_id == account_id))
    for model in (ClientOrder, WarehouseStock, Truck, Client, Product, Warehouse):
        session.exec(delete(model).where(model.account_id == account_id))
    session.commit()

    account = session.get(Account, account_id)
    if account is None:
        accounts = _ensure_accounts(session)
        account = accounts[account_id]
    _insert_reference_data(session, account)
    session.commit()
    return collect_summary(session, account_id=account_id, seeded=True)

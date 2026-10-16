"""SQLModel entities for warehouses, products, stocks, clients and fleet."""

from sqlalchemy import CheckConstraint, UniqueConstraint
from sqlmodel import Field, SQLModel

from app.schemas.enums import DeliveryStatus, RoadType, TruckStatus


class Warehouse(SQLModel, table=True):
    """Multi-warehouse agroholding hub in the Kaluga region."""

    __tablename__ = "warehouse"

    id: int | None = Field(default=None, primary_key=True)
    name: str = Field(max_length=100, index=True)
    lat: float = Field(ge=-90.0, le=90.0)
    lon: float = Field(ge=-180.0, le=180.0)
    address: str = Field(default="", max_length=255)
    is_active: bool = Field(default=True, index=True)


class Product(SQLModel, table=True):
    """Perishable crop reference with its spoilage rate."""

    __tablename__ = "product"

    id: int | None = Field(default=None, primary_key=True)
    code: str = Field(max_length=32, unique=True, index=True)
    name: str = Field(max_length=100)
    base_spoilage_rate: float = Field(gt=0.0)
    optimal_temp_c: float
    base_cost_rub: float = Field(gt=0.0)


class WarehouseStock(SQLModel, table=True):
    """Available batch of one product on one warehouse."""

    __tablename__ = "warehouse_stock"
    __table_args__ = (
        UniqueConstraint("warehouse_id", "product_id", name="uq_stock_warehouse_product"),
        CheckConstraint("available_kg >= 0", name="ck_stock_available_non_negative"),
        CheckConstraint(
            "initial_freshness >= 0.5 AND initial_freshness <= 1.0",
            name="ck_stock_freshness_range",
        ),
    )

    id: int | None = Field(default=None, primary_key=True)
    warehouse_id: int = Field(foreign_key="warehouse.id", index=True)
    product_id: int = Field(foreign_key="product.id", index=True)
    available_kg: float = Field(ge=0.0)
    initial_freshness: float = Field(default=1.0, ge=0.5, le=1.0)


class Client(SQLModel, table=True):
    """B2B buyer with a concrete approach road type."""

    __tablename__ = "client"
    __table_args__ = (
        CheckConstraint("road_type IN ('asphalt', 'dirt')", name="ck_client_road_type"),
    )

    id: int | None = Field(default=None, primary_key=True)
    name: str = Field(max_length=120, index=True)
    lat: float = Field(ge=-90.0, le=90.0)
    lon: float = Field(ge=-180.0, le=180.0)
    road_type: str = Field(default=RoadType.ASPHALT.value, max_length=16, index=True)
    address: str = Field(default="", max_length=255)


class ClientOrder(SQLModel, table=True):
    """Requested volume of one crop placed by a client."""

    __tablename__ = "client_order"
    __table_args__ = (
        CheckConstraint("requested_kg > 0", name="ck_order_requested_positive"),
        CheckConstraint("purchase_price_rub > 0", name="ck_order_price_positive"),
        CheckConstraint("unmet_penalty_rub >= 0", name="ck_order_penalty_non_negative"),
        CheckConstraint(
            "delivery_status IN ('pending', 'delivered')",
            name="ck_order_delivery_status",
        ),
    )

    id: int | None = Field(default=None, primary_key=True)
    client_id: int = Field(foreign_key="client.id", index=True)
    product_id: int = Field(foreign_key="product.id", index=True)
    requested_kg: float = Field(gt=0.0)
    purchase_price_rub: float = Field(gt=0.0)
    unmet_penalty_rub: float = Field(default=0.0, ge=0.0)
    delivery_status: str = Field(
        default=DeliveryStatus.PENDING.value,
        max_length=16,
        index=True,
    )


class Truck(SQLModel, table=True):
    """Fleet unit with capacity, reefer flag and dirt road permission."""

    __tablename__ = "truck"
    __table_args__ = (
        CheckConstraint("capacity_kg > 0", name="ck_truck_capacity_positive"),
        CheckConstraint("cruise_speed_kmh > 0", name="ck_truck_speed_positive"),
        CheckConstraint("cost_per_km_rub >= 0", name="ck_truck_cost_non_negative"),
        CheckConstraint("fixed_trip_cost_rub >= 0", name="ck_truck_fixed_cost_non_negative"),
        CheckConstraint("status IN ('active', 'broken')", name="ck_truck_status"),
    )

    id: int | None = Field(default=None, primary_key=True)
    name: str = Field(max_length=100)
    plate_number: str = Field(max_length=20, unique=True, index=True)
    warehouse_id: int = Field(foreign_key="warehouse.id", index=True)
    capacity_kg: float = Field(gt=0.0)
    cruise_speed_kmh: float = Field(gt=0.0)
    cost_per_km_rub: float = Field(ge=0.0)
    fixed_trip_cost_rub: float = Field(ge=0.0)
    has_reefer: bool = Field(default=False)
    can_use_dirt: bool = Field(default=False)
    status: str = Field(default=TruckStatus.ACTIVE.value, max_length=16, index=True)

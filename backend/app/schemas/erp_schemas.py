from typing import Literal

from pydantic import Field

from app.schemas.base import APIModel
from app.schemas.enums import DeliveryStatus, RoadType, TruckStatus


class WarehouseResponse(APIModel):
    id: int
    name: str
    lat: float
    lon: float
    address: str
    is_active: bool = True


class ProductResponse(APIModel):
    id: int
    name: str
    code: str
    base_spoilage_rate: float = Field(ge=0.0)
    optimal_temp_c: float
    base_cost_rub: float = Field(gt=0.0)


class WarehouseStockResponse(APIModel):
    id: int
    warehouse_id: int
    product_id: int
    available_kg: float = Field(ge=0.0)
    initial_freshness: float = Field(ge=0.5, le=1.0)


class ClientResponse(APIModel):
    id: int
    name: str
    lat: float
    lon: float
    road_type: RoadType
    address: str


class ClientOrderResponse(APIModel):
    id: int
    client_id: int
    product_id: int
    requested_kg: float = Field(gt=0.0)
    purchase_price_rub: float = Field(gt=0.0)
    unmet_penalty_rub: float = Field(ge=0.0)
    delivered_kg: float = Field(default=0.0, ge=0.0)
    delivery_status: DeliveryStatus = DeliveryStatus.PENDING


class OrderAssignmentResponse(APIModel):
    """Оптимальная машина и маршрут для одной заявки (раздел «В работе»)."""

    order_id: int = Field(gt=0)
    truck_id: int = Field(gt=0)
    truck_name: str
    warehouse_id: int = Field(gt=0)
    warehouse_name: str
    shipped_kg: float = Field(ge=0.0)
    distance_km: float = Field(ge=0.0)
    duration_min: float = Field(ge=0.0)
    trip_cost_rub: float = Field(ge=0.0)
    spoilage_loss_rub: float = Field(ge=0.0)
    total_cost_rub: float = Field(ge=0.0)
    expected_freshness: float = Field(ge=0.0, le=1.0)


class TruckResponse(APIModel):
    id: int
    name: str
    plate_number: str
    warehouse_id: int
    capacity_kg: float = Field(gt=0.0)
    cruise_speed_kmh: float = Field(gt=0.0)
    cost_per_km_rub: float = Field(ge=0.0)
    fixed_trip_cost_rub: float = Field(ge=0.0)
    has_reefer: bool
    has_insulation: bool = False
    can_use_dirt: bool
    status: TruckStatus = TruckStatus.ACTIVE


class ERPStateResponse(APIModel):
    warehouses: list[WarehouseResponse] = Field(default_factory=list)
    products: list[ProductResponse] = Field(default_factory=list)
    stocks: list[WarehouseStockResponse] = Field(default_factory=list)
    clients: list[ClientResponse] = Field(default_factory=list)
    orders: list[ClientOrderResponse] = Field(default_factory=list)
    trucks: list[TruckResponse] = Field(default_factory=list)


class DemoResetResponse(APIModel):
    status: Literal["ok"] = "ok"
    warehouses: int = Field(ge=0)
    products: int = Field(ge=0)
    stocks: int = Field(ge=0)
    clients: int = Field(ge=0)
    orders: int = Field(ge=0)
    trucks: int = Field(ge=0)
    seeded: bool = True


class ClientOrderPatch(APIModel):
    purchase_price_rub: float | None = Field(default=None, gt=0.0)
    delivery_status: DeliveryStatus | None = None


class TruckPatch(APIModel):
    status: TruckStatus


class WarehouseStockPatch(APIModel):
    available_kg: float = Field(ge=0.0)

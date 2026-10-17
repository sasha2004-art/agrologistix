"""Схемы ручного создания справочников и заявок.

Создание — это мутация, поэтому поля строгие: сервер не должен принимать
справочник, который потом сломает расчёт (нулевая вместимость, отрицательная
цена, неизвестный тип дороги).
"""

from pydantic import Field

from app.schemas.base import APIModel
from app.schemas.enums import DeliveryStatus, RoadType, TruckStatus


class ProductCreate(APIModel):
    """Библиотека товаров: культура с параметрами порчи."""

    code: str = Field(min_length=1, max_length=32)
    name: str = Field(min_length=1, max_length=100)
    # Доля потери свежести за час при базовой температуре: 0.02 (огурец) … 0.08 (клубника).
    base_spoilage_rate: float = Field(gt=0.0, le=1.0)
    optimal_temp_c: float = Field(ge=-30.0, le=40.0)
    base_cost_rub: float = Field(gt=0.0)


class ClientCreate(APIModel):
    """Магазин или склад-получатель с точкой на карте."""

    name: str = Field(min_length=1, max_length=120)
    lat: float = Field(ge=-90.0, le=90.0)
    lon: float = Field(ge=-180.0, le=180.0)
    road_type: RoadType = RoadType.ASPHALT
    address: str = Field(default="", max_length=255)


class TruckCreate(APIModel):
    """Машина автопарка со стоимостью километра и оснащением."""

    name: str = Field(min_length=1, max_length=100)
    plate_number: str = Field(min_length=1, max_length=20)
    warehouse_id: int = Field(gt=0)
    capacity_kg: float = Field(gt=0.0)
    cruise_speed_kmh: float = Field(gt=0.0, le=120.0)
    cost_per_km_rub: float = Field(ge=0.0)
    fixed_trip_cost_rub: float = Field(ge=0.0)
    has_reefer: bool = False
    has_insulation: bool = False
    can_use_dirt: bool = False
    status: TruckStatus = TruckStatus.ACTIVE


class ClientOrderCreate(APIModel):
    """Новая заявка: спрос появляется в плане со статусом «В плане»."""

    client_id: int = Field(gt=0)
    product_id: int = Field(gt=0)
    requested_kg: float = Field(gt=0.0)
    purchase_price_rub: float = Field(gt=0.0)
    unmet_penalty_rub: float = Field(default=0.0, ge=0.0)
    delivery_status: DeliveryStatus = DeliveryStatus.PENDING


class WarehouseStockCreate(APIModel):
    """Партия товара на складе: сколько есть и насколько свежая."""

    warehouse_id: int = Field(gt=0)
    product_id: int = Field(gt=0)
    available_kg: float = Field(ge=0.0)
    initial_freshness: float = Field(default=1.0, ge=0.5, le=1.0)

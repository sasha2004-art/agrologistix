"""Схемы ручного создания справочников и заявок."""

from pydantic import Field, field_validator

from app.schemas.base import APIModel
from app.schemas.enums import RoadType, TruckStatus


class ProductCreate(APIModel):
    """Библиотека товаров: культура с параметрами порчи."""

    code: str = Field(min_length=1, max_length=32)
    name: str = Field(min_length=1, max_length=100)
    # Доля потери свежести за час при базовой температуре.
    base_spoilage_rate: float = Field(gt=0.0, le=1.0, allow_inf_nan=False)
    optimal_temp_c: float = Field(ge=-30.0, le=40.0, allow_inf_nan=False)
    base_cost_rub: float = Field(gt=0.0, allow_inf_nan=False)

    @field_validator("code", mode="before")
    @classmethod
    def normalize_code(cls, value: str) -> str:
        if not isinstance(value, str):
            return value
        normalized = value.strip().casefold()
        if not normalized:
            raise ValueError("code must not be blank")
        return normalized

    @field_validator("name", mode="before")
    @classmethod
    def strip_name(cls, value: str) -> str:
        if not isinstance(value, str):
            return value
        normalized = value.strip()
        if not normalized:
            raise ValueError("name must not be blank")
        return normalized


class ClientCreate(APIModel):
    """Магазин или склад-получатель с точкой на карте."""

    name: str = Field(min_length=1, max_length=120)
    lat: float = Field(ge=-90.0, le=90.0, allow_inf_nan=False)
    lon: float = Field(ge=-180.0, le=180.0, allow_inf_nan=False)
    road_type: RoadType = RoadType.ASPHALT
    address: str = Field(default="", max_length=255)

    @field_validator("name", mode="before")
    @classmethod
    def strip_name(cls, value: str) -> str:
        if not isinstance(value, str):
            return value
        normalized = value.strip()
        if not normalized:
            raise ValueError("name must not be blank")
        return normalized

    @field_validator("address", mode="before")
    @classmethod
    def strip_address(cls, value: str) -> str:
        return value.strip() if isinstance(value, str) else value


class TruckCreate(APIModel):
    """Машина автопарка со стоимостью километра и оснащением."""

    name: str = Field(min_length=1, max_length=100)
    plate_number: str = Field(min_length=1, max_length=20)
    warehouse_id: int = Field(gt=0)
    capacity_kg: float = Field(gt=0.0, allow_inf_nan=False)
    cruise_speed_kmh: float = Field(gt=0.0, le=120.0, allow_inf_nan=False)
    cost_per_km_rub: float = Field(ge=0.0, allow_inf_nan=False)
    fixed_trip_cost_rub: float = Field(ge=0.0, allow_inf_nan=False)
    has_reefer: bool = False
    has_insulation: bool = False
    can_use_dirt: bool = False
    status: TruckStatus = TruckStatus.ACTIVE

    @field_validator("name", mode="before")
    @classmethod
    def strip_name(cls, value: str) -> str:
        if not isinstance(value, str):
            return value
        normalized = value.strip()
        if not normalized:
            raise ValueError("name must not be blank")
        return normalized

    @field_validator("plate_number", mode="before")
    @classmethod
    def normalize_plate(cls, value: str) -> str:
        if not isinstance(value, str):
            return value
        normalized = value.strip().upper()
        if not normalized:
            raise ValueError("plate_number must not be blank")
        return normalized


class ClientOrderCreate(APIModel):
    """Новая заявка: спрос появляется в плане со статусом «В плане»."""

    client_id: int = Field(gt=0)
    product_id: int = Field(gt=0)
    requested_kg: float = Field(gt=0.0, allow_inf_nan=False)
    purchase_price_rub: float = Field(gt=0.0, allow_inf_nan=False)
    unmet_penalty_rub: float = Field(default=0.0, ge=0.0, allow_inf_nan=False)


class WarehouseStockCreate(APIModel):
    """Партия товара на складе: сколько есть и насколько свежий урожай."""

    warehouse_id: int = Field(gt=0)
    product_id: int = Field(gt=0)
    available_kg: float = Field(ge=0.0, allow_inf_nan=False)
    initial_freshness: float = Field(default=1.0, ge=0.5, le=1.0, allow_inf_nan=False)

"""Ручное создание: библиотека товаров, магазины, машины, заявки, остатки.

Раньше ERP-состояние приходило только из seed, а диспетчер мог лишь править
существующие строки. Здесь появляется вторая половина работы со справочником:
создание с проверкой ссылок и уникальных полей.
"""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlmodel import Session, SQLModel, select

from app.core.database import get_session
from app.core.security import AccessContext
from app.models.erp_models import (
    Client,
    ClientOrder,
    Product,
    Truck,
    Warehouse,
    WarehouseStock,
)
from app.schemas.enums import DeliveryStatus
from app.schemas.erp_create_schemas import (
    ClientCreate,
    ClientOrderCreate,
    ProductCreate,
    TruckCreate,
    WarehouseStockCreate,
)
from app.schemas.erp_schemas import (
    ClientOrderResponse,
    ClientResponse,
    ProductResponse,
    TruckResponse,
    WarehouseStockResponse,
)
from app.schemas.error_schemas import APIErrorResponse

router = APIRouter(prefix="/erp", tags=["erp"])

SessionDependency = Annotated[Session, Depends(get_session)]

_CREATED_RESPONSES: dict[int | str, dict[str, object]] = {
    status.HTTP_404_NOT_FOUND: {
        "model": APIErrorResponse,
        "description": "Referenced entity was not found",
    },
    status.HTTP_409_CONFLICT: {
        "model": APIErrorResponse,
        "description": "Entity with the same key already exists",
    },
}


def _require[EntityT: SQLModel](
    session: Session, model: type[EntityT], entity_id: int, label: str
) -> EntityT:
    """Возвращает сущность по id или 404 с человекочитаемым названием."""
    entity = session.get(model, entity_id)
    if entity is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"{label} №{entity_id} не найден",
        )
    return entity


def _conflict(detail: str) -> HTTPException:
    return HTTPException(status_code=status.HTTP_409_CONFLICT, detail=detail)


@router.post(
    "/products",
    response_model=ProductResponse,
    status_code=status.HTTP_201_CREATED,
    responses=_CREATED_RESPONSES,
    summary="Add a product to the catalogue",
)
def create_product(
    payload: ProductCreate,
    _context: AccessContext,
    session: SessionDependency,
) -> ProductResponse:
    code = payload.code.strip()
    existing = session.exec(select(Product).where(Product.code == code)).first()
    if existing is not None:
        raise _conflict(f"Товар с кодом «{code}» уже есть в библиотеке")

    product = Product(
        code=code,
        name=payload.name.strip(),
        base_spoilage_rate=payload.base_spoilage_rate,
        optimal_temp_c=payload.optimal_temp_c,
        base_cost_rub=payload.base_cost_rub,
    )
    session.add(product)
    session.commit()
    session.refresh(product)
    return ProductResponse.model_validate(product)


@router.post(
    "/clients",
    response_model=ClientResponse,
    status_code=status.HTTP_201_CREATED,
    responses=_CREATED_RESPONSES,
    summary="Add a shop with its map point",
)
def create_client(
    payload: ClientCreate,
    _context: AccessContext,
    session: SessionDependency,
) -> ClientResponse:
    client = Client(
        name=payload.name.strip(),
        lat=payload.lat,
        lon=payload.lon,
        road_type=payload.road_type.value,
        address=payload.address.strip(),
    )
    session.add(client)
    session.commit()
    session.refresh(client)
    return ClientResponse.model_validate(client)


@router.post(
    "/trucks",
    response_model=TruckResponse,
    status_code=status.HTTP_201_CREATED,
    responses=_CREATED_RESPONSES,
    summary="Add a truck to the fleet",
)
def create_truck(
    payload: TruckCreate,
    _context: AccessContext,
    session: SessionDependency,
) -> TruckResponse:
    warehouse = _require(session, Warehouse, payload.warehouse_id, "Склад")
    if not warehouse.is_active:
        raise _conflict(f"Склад «{warehouse.name}» выключен: машину к нему не привязать")

    plate = payload.plate_number.strip().upper()
    existing = session.exec(select(Truck).where(Truck.plate_number == plate)).first()
    if existing is not None:
        raise _conflict(f"Машина с номером «{plate}» уже есть в автопарке")

    truck = Truck(
        name=payload.name.strip(),
        plate_number=plate,
        warehouse_id=payload.warehouse_id,
        capacity_kg=payload.capacity_kg,
        cruise_speed_kmh=payload.cruise_speed_kmh,
        cost_per_km_rub=payload.cost_per_km_rub,
        fixed_trip_cost_rub=payload.fixed_trip_cost_rub,
        has_reefer=payload.has_reefer,
        has_insulation=payload.has_insulation,
        can_use_dirt=payload.can_use_dirt,
        status=payload.status.value,
    )
    session.add(truck)
    session.commit()
    session.refresh(truck)
    return TruckResponse.model_validate(truck)


@router.post(
    "/orders",
    response_model=ClientOrderResponse,
    status_code=status.HTTP_201_CREATED,
    responses=_CREATED_RESPONSES,
    summary="Add a client order",
)
def create_order(
    payload: ClientOrderCreate,
    _context: AccessContext,
    session: SessionDependency,
) -> ClientOrderResponse:
    _require(session, Client, payload.client_id, "Покупатель")
    _require(session, Product, payload.product_id, "Товар")

    order = ClientOrder(
        client_id=payload.client_id,
        product_id=payload.product_id,
        requested_kg=payload.requested_kg,
        purchase_price_rub=payload.purchase_price_rub,
        unmet_penalty_rub=payload.unmet_penalty_rub,
        delivered_kg=0.0,
        delivery_status=DeliveryStatus.PENDING.value,
    )
    session.add(order)
    session.commit()
    session.refresh(order)
    return ClientOrderResponse.model_validate(order)


@router.post(
    "/stocks",
    response_model=WarehouseStockResponse,
    status_code=status.HTTP_201_CREATED,
    responses=_CREATED_RESPONSES,
    summary="Add a stock batch to a warehouse",
)
def create_stock(
    payload: WarehouseStockCreate,
    _context: AccessContext,
    session: SessionDependency,
) -> WarehouseStockResponse:
    _require(session, Warehouse, payload.warehouse_id, "Склад")
    _require(session, Product, payload.product_id, "Товар")

    existing = session.exec(
        select(WarehouseStock).where(
            WarehouseStock.warehouse_id == payload.warehouse_id,
            WarehouseStock.product_id == payload.product_id,
        )
    ).first()
    if existing is not None:
        raise _conflict(
            "Партия этого товара на складе уже есть — измените остаток вместо новой строки"
        )

    stock = WarehouseStock(
        warehouse_id=payload.warehouse_id,
        product_id=payload.product_id,
        available_kg=payload.available_kg,
        initial_freshness=payload.initial_freshness,
    )
    session.add(stock)
    session.commit()
    session.refresh(stock)
    return WarehouseStockResponse.model_validate(stock)

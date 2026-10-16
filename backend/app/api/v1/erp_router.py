from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlmodel import Session, SQLModel, select

from app.core.database import get_session
from app.core.security import AccessContext, AdminContext
from app.models.erp_models import (
    Client,
    ClientOrder,
    Product,
    Truck,
    Warehouse,
    WarehouseStock,
)
from app.schemas.erp_schemas import (
    ClientOrderPatch,
    ClientOrderResponse,
    ClientResponse,
    DemoResetResponse,
    ERPStateResponse,
    ProductResponse,
    TruckPatch,
    TruckResponse,
    WarehouseResponse,
    WarehouseStockPatch,
    WarehouseStockResponse,
)
from app.schemas.error_schemas import APIErrorResponse
from app.services.seed_kaluga import reset_demo_database
from app.services.weather_service import reset_weather_cache

router = APIRouter(prefix="/erp", tags=["erp"])
system_router = APIRouter(prefix="/system", tags=["system"])

SessionDependency = Annotated[Session, Depends(get_session)]

_NOT_FOUND_RESPONSE = {"model": APIErrorResponse, "description": "Entity was not found"}
_BAD_REQUEST_RESPONSE = {"model": APIErrorResponse, "description": "Request cannot be applied"}


def _get_or_404[EntityT: SQLModel](
    session: Session, model: type[EntityT], entity_id: int, label: str
) -> EntityT:
    entity = session.get(model, entity_id)
    if entity is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"{label} with id {entity_id} was not found",
        )
    return entity


@router.get(
    "/state",
    response_model=ERPStateResponse,
    summary="Read the full ERP state used by the solver",
)
def read_erp_state(_context: AccessContext, session: SessionDependency) -> ERPStateResponse:
    warehouses = session.exec(select(Warehouse).order_by(Warehouse.id)).all()
    products = session.exec(select(Product).order_by(Product.id)).all()
    stocks = session.exec(select(WarehouseStock).order_by(WarehouseStock.id)).all()
    clients = session.exec(select(Client).order_by(Client.id)).all()
    orders = session.exec(select(ClientOrder).order_by(ClientOrder.id)).all()
    trucks = session.exec(select(Truck).order_by(Truck.id)).all()

    return ERPStateResponse(
        warehouses=[WarehouseResponse.model_validate(item) for item in warehouses],
        products=[ProductResponse.model_validate(item) for item in products],
        stocks=[WarehouseStockResponse.model_validate(item) for item in stocks],
        clients=[ClientResponse.model_validate(item) for item in clients],
        orders=[ClientOrderResponse.model_validate(item) for item in orders],
        trucks=[TruckResponse.model_validate(item) for item in trucks],
    )


@router.patch(
    "/orders/{order_id}",
    response_model=ClientOrderResponse,
    responses={
        status.HTTP_400_BAD_REQUEST: _BAD_REQUEST_RESPONSE,
        status.HTTP_404_NOT_FOUND: _NOT_FOUND_RESPONSE,
    },
    summary="Update purchase price or delivery status of one client order",
)
def patch_client_order(
    order_id: int,
    payload: ClientOrderPatch,
    _context: AccessContext,
    session: SessionDependency,
) -> ClientOrderResponse:
    order = _get_or_404(session, ClientOrder, order_id, "Client order")

    updated = False
    if payload.purchase_price_rub is not None:
        order.purchase_price_rub = payload.purchase_price_rub
        updated = True
    if payload.delivery_status is not None:
        order.delivery_status = payload.delivery_status.value
        updated = True

    if not updated:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Request body must contain at least one field to update",
        )

    session.add(order)
    session.commit()
    session.refresh(order)
    return ClientOrderResponse.model_validate(order)


@router.patch(
    "/trucks/{truck_id}",
    response_model=TruckResponse,
    responses={status.HTTP_404_NOT_FOUND: _NOT_FOUND_RESPONSE},
    summary="Switch a truck between active and broken status",
)
def patch_truck(
    truck_id: int,
    payload: TruckPatch,
    _context: AccessContext,
    session: SessionDependency,
) -> TruckResponse:
    truck = _get_or_404(session, Truck, truck_id, "Truck")
    truck.status = payload.status.value

    session.add(truck)
    session.commit()
    session.refresh(truck)
    return TruckResponse.model_validate(truck)


@router.patch(
    "/stocks/{stock_id}",
    response_model=WarehouseStockResponse,
    responses={status.HTTP_404_NOT_FOUND: _NOT_FOUND_RESPONSE},
    summary="Update the available weight of one warehouse stock batch",
)
def patch_warehouse_stock(
    stock_id: int,
    payload: WarehouseStockPatch,
    _context: AccessContext,
    session: SessionDependency,
) -> WarehouseStockResponse:
    stock = _get_or_404(session, WarehouseStock, stock_id, "Warehouse stock")
    stock.available_kg = payload.available_kg

    session.add(stock)
    session.commit()
    session.refresh(stock)
    return WarehouseStockResponse.model_validate(stock)


@system_router.post(
    "/reset-demo",
    response_model=DemoResetResponse,
    summary="Rebuild the Kaluga demo dataset (administrator only)",
)
def reset_demo(_context: AdminContext, session: SessionDependency) -> DemoResetResponse:
    summary = reset_demo_database(session)
    reset_weather_cache()
    return DemoResetResponse(
        warehouses=summary.warehouses,
        products=summary.products,
        stocks=summary.stocks,
        clients=summary.clients,
        orders=summary.orders,
        trucks=summary.trucks,
        seeded=summary.seeded,
    )

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
from app.models.run_models import DeliveredOrderStock, RouteStop
from app.schemas.enums import DeliveryStatus
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
_CONFLICT_RESPONSE = {"model": APIErrorResponse, "description": "Persisted state is inconsistent"}

# Tolerated rounding drift for kilogram comparisons.
_KG_EPSILON = 1e-6


def _plan_consumption(
    session: Session, order: ClientOrder, remaining_kg: float
) -> dict[int, float]:
    """Warehouse quantities shipped by the latest plan for this order."""

    stops = session.exec(
        select(RouteStop).where(RouteStop.order_id == order.id).order_by(RouteStop.run_id.desc())
    ).all()
    if not stops:
        return {}

    latest_run_id = stops[0].run_id
    planned: dict[int, float] = {}
    for stop in stops:
        if stop.run_id != latest_run_id:
            break
        if stop.product_id != order.product_id:
            continue
        planned[stop.warehouse_id] = planned.get(stop.warehouse_id, 0.0) + stop.shipped_kg

    consumed: dict[int, float] = {}
    budget = min(remaining_kg, sum(planned.values()))
    for warehouse_id, shipped_kg in planned.items():
        if budget <= _KG_EPSILON:
            break
        take = min(shipped_kg, budget)
        consumed[warehouse_id] = take
        budget -= take
    return consumed


def _consume_stock(session: Session, order: ClientOrder, consumed: dict[int, float]) -> float:
    """Write off warehouse stock and journal exactly what was delivered."""

    stocks = session.exec(
        select(WarehouseStock).where(
            WarehouseStock.product_id == order.product_id,
            WarehouseStock.warehouse_id.in_(consumed),
        )
    ).all()
    stocks_by_warehouse = {stock.warehouse_id: stock for stock in stocks}

    total_kg = 0.0
    for warehouse_id, shipped_kg in consumed.items():
        stock = stocks_by_warehouse.get(warehouse_id)
        if stock is None or stock.available_kg + _KG_EPSILON < shipped_kg:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Остатки на складе изменились после расчёта — обновите план и повторите",
            )
        stock.available_kg = max(0.0, stock.available_kg - shipped_kg)
        session.add(stock)
        session.add(
            DeliveredOrderStock(
                order_id=int(order.id or 0),
                stock_id=int(stock.id or 0),
                shipped_kg=shipped_kg,
            )
        )
        total_kg += shipped_kg
    return total_kg


def _apply_delivered_status(session: Session, order: ClientOrder) -> None:
    """Spend stock for the delivered volume and keep the remaining demand alive.

    A plan is required to know *where* the cargo came from. Without any stored
    plan the order is closed as delivered outside the system, so the demo stays
    usable while the stock journal keeps the write-off traceable once a plan
    exists. A partial plan keeps the order ``pending`` with the leftover demand.
    """

    remaining_kg = max(0.0, order.requested_kg - order.delivered_kg)
    if remaining_kg <= _KG_EPSILON:
        order.delivery_status = DeliveryStatus.DELIVERED.value
        return

    consumed = _plan_consumption(session, order, remaining_kg)
    if not consumed:
        order.delivered_kg = order.requested_kg
        order.delivery_status = DeliveryStatus.DELIVERED.value
        return

    delivered_kg = _consume_stock(session, order, consumed)
    order.delivered_kg = min(order.requested_kg, order.delivered_kg + delivered_kg)
    if order.requested_kg - order.delivered_kg <= _KG_EPSILON:
        order.delivery_status = DeliveryStatus.DELIVERED.value
    else:
        order.delivery_status = DeliveryStatus.PENDING.value


def _restore_delivered_stock(session: Session, order: ClientOrder) -> None:
    """Undo the write-off when an order is switched back to ``pending``."""

    deliveries = session.exec(
        select(DeliveredOrderStock).where(DeliveredOrderStock.order_id == order.id)
    ).all()
    for delivery in deliveries:
        stock = session.get(WarehouseStock, delivery.stock_id)
        if stock is not None:
            stock.available_kg += delivery.shipped_kg
            session.add(stock)
        session.delete(delivery)
    order.delivered_kg = 0.0


def _get_or_404[EntityT: SQLModel](
    session: Session, model: type[EntityT], entity_id: int, label: str
) -> EntityT:
    entity = session.get(model, entity_id)
    if entity is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"{label} №{entity_id} не найден",
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
    order = _get_or_404(session, ClientOrder, order_id, "Заказ")

    updated = False
    if payload.purchase_price_rub is not None:
        order.purchase_price_rub = payload.purchase_price_rub
        updated = True
    if payload.delivery_status is not None:
        target_status = payload.delivery_status.value
        if target_status == DeliveryStatus.DELIVERED.value:
            if target_status != order.delivery_status:
                _apply_delivered_status(session, order)
        else:
            # Restore also for partial deliveries, where the status stayed pending.
            if order.delivered_kg > 0.0:
                _restore_delivered_stock(session, order)
            order.delivery_status = DeliveryStatus.PENDING.value
        updated = True

    if not updated:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Укажите хотя бы одно поле для изменения",
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
    truck = _get_or_404(session, Truck, truck_id, "Машина")
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
    stock = _get_or_404(session, WarehouseStock, stock_id, "Партия")
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

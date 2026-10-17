from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlmodel import Session, SQLModel, select

from app.core.config import Settings, get_settings
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
from app.models.run_models import DeliveredOrderStock, FixedAssignment, RouteStop
from app.schemas.enums import DeliveryStatus
from app.schemas.erp_schemas import (
    ClientOrderPatch,
    ClientOrderResponse,
    ClientResponse,
    DemoResetResponse,
    ERPStateResponse,
    FixedAssignmentResponse,
    OrderAssignmentResponse,
    ProductPatch,
    ProductResponse,
    TruckPatch,
    TruckResponse,
    WarehouseResponse,
    WarehouseStockPatch,
    WarehouseStockResponse,
)
from app.schemas.error_schemas import APIErrorResponse
from app.schemas.solver_schemas import RoutePoint
from app.services.order_assignment import (
    assign_order,
    assignment_geometry,
    clear_fixed_assignment,
    load_fixed_assignments,
    save_fixed_assignment,
)
from app.services.seed_kaluga import reset_demo_database
from app.services.weather_service import get_current_weather, reset_weather_cache

router = APIRouter(prefix="/erp", tags=["erp"])
system_router = APIRouter(prefix="/system", tags=["system"])

SessionDependency = Annotated[Session, Depends(get_session)]
SettingsDependency = Annotated[Settings, Depends(get_settings)]

_NOT_FOUND_RESPONSE = {"model": APIErrorResponse, "description": "Entity was not found"}
_BAD_REQUEST_RESPONSE = {"model": APIErrorResponse, "description": "Request cannot be applied"}
_CONFLICT_RESPONSE = {"model": APIErrorResponse, "description": "Persisted state is inconsistent"}

# Tolerated rounding drift for kilogram comparisons.
_KG_EPSILON = 1e-6


def _plan_consumption(
    session: Session, order: ClientOrder, remaining_kg: float, *, account_id: int
) -> dict[int, float]:
    """Warehouse quantities shipped by the latest plan for this order."""

    stops = session.exec(
        select(RouteStop)
        .where(RouteStop.account_id == account_id, RouteStop.order_id == order.id)
        .order_by(RouteStop.run_id.desc())
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


def _fixed_consumption(
    session: Session, order: ClientOrder, remaining_kg: float, *, account_id: int
) -> dict[int, float]:
    """Warehouse quantities of the fixed route chosen when the order went in progress."""

    fixed = session.exec(
        select(FixedAssignment).where(
            FixedAssignment.account_id == account_id, FixedAssignment.order_id == order.id
        )
    ).first()
    if fixed is None:
        return {}
    return {fixed.warehouse_id: min(remaining_kg, fixed.shipped_kg)}


def _consume_stock(session: Session, order: ClientOrder, consumed: dict[int, float]) -> float:
    """Write off warehouse stock and journal exactly what was delivered."""

    stocks = session.exec(
        select(WarehouseStock).where(
            WarehouseStock.account_id == order.account_id,
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
                account_id=order.account_id,
                order_id=int(order.id or 0),
                stock_id=int(stock.id or 0),
                shipped_kg=shipped_kg,
            )
        )
        total_kg += shipped_kg
    return total_kg


def _apply_shipped_status(session: Session, order: ClientOrder, target_status: str) -> None:
    """Списывает отгруженный объём и переводит заявку на новый этап поставки.

    Используется и для «В работе» (`in_progress`), и для «Доставлено»
    (`delivered`): в обоих случаях груз уже уехал со склада, и его нельзя
    распределить повторно. Место отгрузки знает только план, поэтому без
    сохранённого плана заявка считается отгруженной целиком (демо остаётся
    работоспособным, а журнал списаний фиксирует вывоз, когда план есть).
    Частичная отгрузка оставляет остаточный спрос в статусе ``pending``.
    """

    remaining_kg = max(0.0, order.requested_kg - order.delivered_kg)
    if remaining_kg <= _KG_EPSILON:
        order.delivery_status = target_status
        return

    # У заявки «В работе» уже есть зафиксированный маршрут: списываем с его
    # склада, а не с последнего плана. Иначе работаем как раньше — по плану.
    consumed = _fixed_consumption(
        session, order, remaining_kg, account_id=order.account_id
    ) or _plan_consumption(
        session, order, remaining_kg, account_id=order.account_id
    )
    if not consumed:
        order.delivered_kg = order.requested_kg
        order.delivery_status = target_status
        return

    delivered_kg = _consume_stock(session, order, consumed)
    order.delivered_kg = min(order.requested_kg, order.delivered_kg + delivered_kg)
    if order.requested_kg - order.delivered_kg <= _KG_EPSILON:
        order.delivery_status = target_status
    else:
        order.delivery_status = DeliveryStatus.PENDING.value


def _restore_delivered_stock(session: Session, order: ClientOrder) -> None:
    """Undo the write-off when an order is switched back to ``pending``."""

    deliveries = session.exec(
        select(DeliveredOrderStock).where(
            DeliveredOrderStock.account_id == order.account_id,
            DeliveredOrderStock.order_id == order.id,
        )
    ).all()
    for delivery in deliveries:
        stock = session.get(WarehouseStock, delivery.stock_id)
        if stock is not None:
            stock.available_kg += delivery.shipped_kg
            session.add(stock)
        session.delete(delivery)
    order.delivered_kg = 0.0


def _fixed_assignment_response(session: Session, fixed: FixedAssignment) -> FixedAssignmentResponse:
    """Фиксация с именами машины и склада и полилинией для карты."""

    truck = session.exec(
        select(Truck).where(Truck.account_id == fixed.account_id, Truck.id == fixed.truck_id)
    ).first()
    warehouse = session.exec(
        select(Warehouse).where(
            Warehouse.account_id == fixed.account_id, Warehouse.id == fixed.warehouse_id
        )
    ).first()
    return FixedAssignmentResponse(
        order_id=fixed.order_id,
        truck_id=fixed.truck_id,
        truck_name=truck.name if truck else f"Машина {fixed.truck_id}",
        warehouse_id=fixed.warehouse_id,
        warehouse_name=warehouse.name if warehouse else f"Склад {fixed.warehouse_id}",
        client_id=fixed.client_id,
        product_id=fixed.product_id,
        shipped_kg=fixed.shipped_kg,
        distance_km=fixed.distance_km,
        duration_min=fixed.duration_min,
        expected_freshness=fixed.expected_freshness,
        trip_cost_rub=fixed.trip_cost_rub,
        geometry=[RoutePoint(lat=lat, lon=lon) for lat, lon in assignment_geometry(fixed)],
    )


def _get_or_404[EntityT: SQLModel](
    session: Session, model: type[EntityT], entity_id: int, label: str, *, account_id: int
) -> EntityT:
    entity = session.exec(
        select(model).where(getattr(model, "account_id") == account_id, model.id == entity_id)
    ).first()
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
def read_erp_state(context: AccessContext, session: SessionDependency) -> ERPStateResponse:
    account_id = context.account_id
    warehouses = session.exec(
        select(Warehouse).where(Warehouse.account_id == account_id).order_by(Warehouse.id)
    ).all()
    products = session.exec(
        select(Product).where(Product.account_id == account_id).order_by(Product.id)
    ).all()
    stocks = session.exec(
        select(WarehouseStock)
        .where(WarehouseStock.account_id == account_id)
        .order_by(WarehouseStock.id)
    ).all()
    clients = session.exec(
        select(Client).where(Client.account_id == account_id).order_by(Client.id)
    ).all()
    orders = session.exec(
        select(ClientOrder).where(ClientOrder.account_id == account_id).order_by(ClientOrder.id)
    ).all()
    trucks = session.exec(select(Truck).where(Truck.account_id == account_id).order_by(Truck.id)).all()
    fixed_assignments = [
        _fixed_assignment_response(session, item)
        for item in load_fixed_assignments(session, account_id=account_id)
    ]

    return ERPStateResponse(
        warehouses=[WarehouseResponse.model_validate(item) for item in warehouses],
        products=[ProductResponse.model_validate(item) for item in products],
        stocks=[WarehouseStockResponse.model_validate(item) for item in stocks],
        clients=[ClientResponse.model_validate(item) for item in clients],
        orders=[ClientOrderResponse.model_validate(item) for item in orders],
        trucks=[TruckResponse.model_validate(item) for item in trucks],
        fixed_assignments=fixed_assignments,
    )


@router.patch(
    "/products/{product_id}",
    response_model=ProductResponse,
    responses={
        status.HTTP_400_BAD_REQUEST: _BAD_REQUEST_RESPONSE,
        status.HTTP_404_NOT_FOUND: _NOT_FOUND_RESPONSE,
    },
    summary="Update the reference cost per kilogram of a product",
)
def patch_product(
    product_id: int,
    payload: ProductPatch,
    _context: AccessContext,
    session: SessionDependency,
) -> ProductResponse:
    product = _get_or_404(session, Product, product_id, "Товар", account_id=_context.account_id)
    product.base_cost_rub = payload.base_cost_rub
    session.add(product)
    session.commit()
    session.refresh(product)
    return ProductResponse.model_validate(product)


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
    order = _get_or_404(session, ClientOrder, order_id, "Заказ", account_id=_context.account_id)

    updated = False
    if payload.purchase_price_rub is not None:
        order.purchase_price_rub = payload.purchase_price_rub
        updated = True
    if payload.delivery_status is not None:
        target_status = payload.delivery_status.value
        if target_status == DeliveryStatus.PENDING.value:
            # Возврат в «В плане» отменяет отгрузку, возвращает сток и снимает фиксацию.
            if order.delivered_kg > 0.0:
                _restore_delivered_stock(session, order)
            clear_fixed_assignment(session, int(order.id or 0), account_id=_context.account_id)
            order.delivery_status = DeliveryStatus.PENDING.value
        else:
            # «В работе» и «Доставлено» — обе стадии уже отгруженного груза.
            _apply_shipped_status(session, order, target_status)
            if target_status == DeliveryStatus.DELIVERED.value:
                # Закрытая заявка больше не участвует в плане: фиксация не нужна.
                clear_fixed_assignment(session, int(order.id or 0), account_id=_context.account_id)
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


@router.post(
    "/orders/{order_id}/assign",
    response_model=OrderAssignmentResponse,
    responses={
        status.HTTP_404_NOT_FOUND: _NOT_FOUND_RESPONSE,
        status.HTTP_409_CONFLICT: _CONFLICT_RESPONSE,
    },
    summary="Pick the cheapest truck and route for one client order",
)
async def assign_client_order(
    order_id: int,
    _context: AccessContext,
    session: SessionDependency,
    settings: SettingsDependency,
) -> OrderAssignmentResponse:
    """Подбирает оптимальную машину и маршрут для заявки, которую берут в работу."""

    order = _get_or_404(session, ClientOrder, order_id, "Заказ", account_id=_context.account_id)
    weather = await get_current_weather(session, settings, account_id=_context.account_id)
    assignment = await assign_order(
        session, settings, order, weather, account_id=_context.account_id
    )
    if assignment is None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                "Нет подходящей машины: проверьте остатки урожая, "
                "допуск на грунт и состояние автопарка"
            ),
        )
    # Маршрут фиксируется: он появится на карте и войдёт в следующий расчёт
    # как готовый рейс, а машина не будет переиспользована.
    save_fixed_assignment(session, assignment, order, account_id=_context.account_id)

    return OrderAssignmentResponse(
        order_id=assignment.order_id,
        truck_id=assignment.truck_id,
        truck_name=assignment.truck_name,
        warehouse_id=assignment.warehouse_id,
        warehouse_name=assignment.warehouse_name,
        shipped_kg=assignment.shipped_kg,
        distance_km=assignment.distance_km,
        duration_min=assignment.duration_min,
        trip_cost_rub=assignment.trip_cost_rub,
        spoilage_loss_rub=assignment.spoilage_loss_rub,
        total_cost_rub=assignment.total_cost_rub,
        expected_freshness=assignment.expected_freshness,
        geometry=[RoutePoint(lat=lat, lon=lon) for lat, lon in assignment.geometry],
    )


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
    truck = _get_or_404(session, Truck, truck_id, "Машина", account_id=_context.account_id)
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
    stock = _get_or_404(
        session, WarehouseStock, stock_id, "Партия", account_id=_context.account_id
    )
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
    summary = reset_demo_database(session, account_id=_context.account_id)
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

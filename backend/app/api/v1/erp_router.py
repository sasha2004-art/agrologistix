from typing import Annotated

from fastapi import APIRouter, Depends
from sqlmodel import Session, select

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
    ClientOrderResponse,
    ClientResponse,
    DemoResetResponse,
    ERPStateResponse,
    ProductResponse,
    TruckResponse,
    WarehouseResponse,
    WarehouseStockResponse,
)
from app.services.seed_kaluga import reset_demo_database

router = APIRouter(prefix="/erp", tags=["erp"])
system_router = APIRouter(prefix="/system", tags=["system"])

SessionDependency = Annotated[Session, Depends(get_session)]


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


@system_router.post(
    "/reset-demo",
    response_model=DemoResetResponse,
    summary="Rebuild the Kaluga demo dataset (administrator only)",
)
def reset_demo(_context: AdminContext, session: SessionDependency) -> DemoResetResponse:
    summary = reset_demo_database(session)
    return DemoResetResponse(
        warehouses=summary.warehouses,
        products=summary.products,
        stocks=summary.stocks,
        clients=summary.clients,
        orders=summary.orders,
        trucks=summary.trucks,
        seeded=summary.seeded,
    )

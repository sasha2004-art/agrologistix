"""Build the pure solver input from the persisted ERP state.

The builder reads warehouses, products, stocks, clients, pending orders and the
fleet, resolves every coordinate pair through the cached distance matrix and
returns an immutable :class:`SolverInput`. The demand of an order is its
outstanding weight (``requested_kg - delivered_kg``), so a partially delivered
order keeps only the leftover demand and the stock write-off is not replanned.
Orders already shipped (``in_progress``) or closed as delivered are passed as
``frozen_order_ids`` so the engine can distinguish them from unmet demand.
"""

from sqlmodel import Session, select

from app.core.config import Settings
from app.models.erp_models import (
    Client,
    ClientOrder,
    Product,
    Truck,
    Warehouse,
    WarehouseStock,
)
from app.schemas.enums import DeliveryStatus, RoadType, TruckStatus
from app.services.distance_matrix import Coordinate, build_distance_matrix
from app.services.order_assignment import assignment_geometry, load_fixed_assignments
from app.services.solver_contract import (
    SolverFixedRoute,
    SolverInput,
    SolverLeg,
    SolverOrder,
    SolverProduct,
    SolverStock,
    SolverTruck,
    SolverWarehouse,
    SolverWeather,
)
from app.services.weather_service import WeatherSnapshot


def remaining_demand_kg(order: ClientOrder) -> float:
    """Outstanding weight of an order after every recorded delivery."""

    return max(0.0, order.requested_kg - order.delivered_kg)


def _fixed_routes(
    session: Session,
    orders: list[ClientOrder],
    clients_by_id: dict[int, Client],
    trucks: list[Truck],
    *,
    account_id: int,
) -> tuple[SolverFixedRoute, ...]:
    """Готовые рейсы из фиксаций: заявка «В работе» со своей машиной и складом.

    Only ``in_progress`` orders become ready-made trips. A fixation of a still
    pending order is a reservation: the stock has not been written off yet and
    the order must stay in the MILP, otherwise a failed status change would
    freeze the cargo out of the plan.
    """

    orders_by_id = {int(order.id or 0): order for order in orders}
    trucks_by_id = {int(truck.id or 0): truck for truck in trucks}
    routes: list[SolverFixedRoute] = []
    for fixed in load_fixed_assignments(session, account_id=account_id):
        order = orders_by_id.get(fixed.order_id)
        client = clients_by_id.get(fixed.client_id)
        if order is None or client is None:
            continue
        if order.delivery_status != DeliveryStatus.IN_PROGRESS:
            continue
        truck = trucks_by_id.get(fixed.truck_id)
        routes.append(
            SolverFixedRoute(
                truck_id=fixed.truck_id,
                truck_name=truck.name if truck is not None else f"Машина {fixed.truck_id}",
                warehouse_id=fixed.warehouse_id,
                order=SolverOrder(
                    order_id=fixed.order_id,
                    client_id=fixed.client_id,
                    product_id=fixed.product_id,
                    requested_kg=fixed.shipped_kg,
                    price_per_kg=order.purchase_price_rub,
                    penalty_per_kg=order.unmet_penalty_rub,
                    road_type=RoadType(client.road_type),
                    latitude=client.lat,
                    longitude=client.lon,
                ),
                shipped_kg=fixed.shipped_kg,
                distance_km=fixed.distance_km,
                duration_min=fixed.duration_min,
                expected_freshness=fixed.expected_freshness,
                trip_cost_rub=fixed.trip_cost_rub,
                geometry=tuple(assignment_geometry(fixed)),
            )
        )
    return tuple(routes)


async def build_solver_input(
    session: Session,
    settings: Settings,
    weather: WeatherSnapshot,
    *,
    account_id: int,
) -> SolverInput:
    """Assemble the engine input from SQLite and the cached route matrix."""

    warehouses = session.exec(
        select(Warehouse)
        .where(Warehouse.account_id == account_id, Warehouse.is_active.is_(True))
        .order_by(Warehouse.id)
    ).all()
    active_warehouse_ids = [int(warehouse.id or 0) for warehouse in warehouses]
    products = session.exec(select(Product).order_by(Product.id)).all()
    # Stock of a deactivated warehouse is not part of the plan and must not be
    # counted by the solver or by the stock-shortage warning.
    stocks = session.exec(
        select(WarehouseStock)
        .where(
            WarehouseStock.account_id == account_id,
            WarehouseStock.warehouse_id.in_(active_warehouse_ids),
        )
        .order_by(WarehouseStock.id)
    ).all()
    clients = session.exec(select(Client).where(Client.account_id == account_id).order_by(Client.id)).all()
    orders = session.exec(
        select(ClientOrder).where(ClientOrder.account_id == account_id).order_by(ClientOrder.id)
    ).all()
    trucks = session.exec(select(Truck).where(Truck.account_id == account_id).order_by(Truck.id)).all()

    clients_by_id = {client.id: client for client in clients}
    # Only points that can appear in the plan are resolved through the distance
    # matrix: delivered orders and fully shipped ones are never routed, so
    # their coordinates must not spend Mapbox requests.
    planned_orders = [
        order
        for order in orders
        if order.delivery_status == DeliveryStatus.PENDING
        and order.client_id in clients_by_id
        and remaining_demand_kg(order) > 0.0
    ]
    points = [
        (warehouse.lat, warehouse.lon) for warehouse in warehouses if warehouse.id is not None
    ]
    points.extend(
        (clients_by_id[order.client_id].lat, clients_by_id[order.client_id].lon)
        for order in planned_orders
        if order.id is not None
    )

    unique_points = list(dict.fromkeys(points))
    legs: list[SolverLeg] = []
    if unique_points:
        coordinates = [Coordinate(lat=lat, lon=lon) for lat, lon in unique_points]
        matrix = await build_distance_matrix(
            session, coordinates, settings, account_id=account_id
        )
        for row_index in range(len(coordinates)):
            for column_index in range(len(coordinates)):
                if row_index == column_index:
                    continue
                leg = matrix[row_index][column_index]
                legs.append(
                    SolverLeg(
                        origin=unique_points[row_index],
                        destination=unique_points[column_index],
                        distance_km=leg.distance_km,
                        base_duration_min=leg.base_duration_min,
                        geometry=tuple(leg.geometry),
                    )
                )

    solver_orders = tuple(
        SolverOrder(
            order_id=int(order.id or 0),
            client_id=order.client_id,
            product_id=order.product_id,
            requested_kg=remaining_demand_kg(order),
            price_per_kg=order.purchase_price_rub,
            penalty_per_kg=order.unmet_penalty_rub,
            road_type=RoadType(clients_by_id[order.client_id].road_type),
            latitude=clients_by_id[order.client_id].lat,
            longitude=clients_by_id[order.client_id].lon,
        )
        for order in planned_orders
        if order.id is not None
    )
    frozen_order_ids = tuple(
        int(order.id or 0)
        for order in orders
        if order.id is not None
        and order.delivery_status in (DeliveryStatus.IN_PROGRESS, DeliveryStatus.DELIVERED)
    )
    fixed_routes = _fixed_routes(session, orders, clients_by_id, trucks, account_id=account_id)

    return SolverInput(
        products=tuple(
            SolverProduct(
                product_id=int(product.id or 0),
                spoilage_rate=product.base_spoilage_rate,
                base_cost_rub=product.base_cost_rub,
                name=product.name,
            )
            for product in products
            if product.id is not None
        ),
        stocks=tuple(
            SolverStock(
                warehouse_id=stock.warehouse_id,
                product_id=stock.product_id,
                available_kg=stock.available_kg,
                initial_freshness=stock.initial_freshness,
            )
            for stock in stocks
            if stock.id is not None
        ),
        orders=solver_orders,
        trucks=tuple(
            SolverTruck(
                truck_id=int(truck.id or 0),
                name=truck.name,
                warehouse_id=truck.warehouse_id,
                capacity_kg=truck.capacity_kg,
                cruise_speed_kmh=truck.cruise_speed_kmh,
                cost_per_km_rub=truck.cost_per_km_rub,
                fixed_trip_cost_rub=truck.fixed_trip_cost_rub,
                has_reefer=truck.has_reefer,
                has_insulation=truck.has_insulation,
                can_use_dirt=truck.can_use_dirt,
                status=TruckStatus(truck.status),
            )
            for truck in trucks
            if truck.id is not None
        ),
        legs=tuple(legs),
        weather=SolverWeather(
            temperature_c=weather.temperature_c,
            precipitation_mm=weather.precipitation_mm,
            mode=weather.mode.value,
        ),
        warehouses=tuple(
            SolverWarehouse(
                warehouse_id=int(warehouse.id or 0),
                name=warehouse.name,
                latitude=warehouse.lat,
                longitude=warehouse.lon,
            )
            for warehouse in warehouses
            if warehouse.id is not None
        ),
        frozen_order_ids=frozen_order_ids,
        fixed_routes=fixed_routes,
        client_split_penalty_rub=settings.solver_client_split_penalty_rub,
        max_stops_per_trip=settings.solver_max_stops_per_trip,
        max_trip_hours=settings.solver_max_trip_hours,
        min_stop_freshness=settings.solver_min_stop_freshness,
        improve_time_budget_sec=settings.solver_improve_time_budget_sec,
        improve_max_evaluations=settings.solver_improve_max_evaluations,
    )

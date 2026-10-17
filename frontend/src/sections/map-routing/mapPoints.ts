/**
 * Точки карты Калужской области: склады и покупатели.
 *
 * Модуль собирает данные из ERP и плана расчёта, не зная о DOM: маркеры
 * (`useMapboxMarkers.ts`) и popup (`mapPopupContent.ts`) читают одну модель.
 */

import type {
  Client,
  ClientOrder,
  DeliveryStatus,
  Product,
  RoadType,
  Warehouse,
} from '@/shared/types/domain'

/** Данные остановки плана для конкретной заявки. */
export interface ClientPlanInfo {
  orderId: number | null
  truckName: string
  color: string
  etaMinutes: number
  expectedFreshness: number
  shippedKg: number
  sequenceOrder: number
  distanceKm: number
  tripLegCostRub: number
}

/** Заявка покупателя: карточка раскрывает подробности по каждой отдельно. */
export interface MapPointOrder {
  orderId: number
  productName: string
  requestedKg: number
  purchasePriceRub: number
  deliveredKg: number
  deliveryStatus: DeliveryStatus
  /** Самый поздний стоп заявки в плане: он же показывается в подробностях. */
  plan: ClientPlanInfo | null
  /** Сколько остановок плана приходится на заявку (дробление между рейсами). */
  planStopsCount: number
}

export interface MapPoint {
  id: string
  kind: 'warehouse' | 'client'
  name: string
  address: string
  coordinates: [number, number]
  roadType: RoadType | null
  deliveryStatus: DeliveryStatus | null
  orderCount: number
  requestedKg: number
  /** Заявки покупателя; у склада список всегда пустой. */
  orders: MapPointOrder[]
  /** Самый поздний стоп рассчитанного плана для этой точки (если план уже есть). */
  plan: ClientPlanInfo | null
  /** Сколько остановок плана попало в эту точку (может быть больше одной). */
  planStopsCount: number
}

export function roadLabel(roadType: RoadType | null): string {
  if (roadType === 'dirt') return 'Грунтовка'
  if (roadType === 'asphalt') return 'Асфальт'
  return ''
}

export function statusLabel(status: DeliveryStatus | null): string {
  if (status === 'delivered') return 'Доставлено'
  if (status === 'pending') return 'В работе'
  return ''
}

function clientStatus(orders: ClientOrder[]): DeliveryStatus | null {
  if (orders.length === 0) return null
  return orders.every((order) => order.delivery_status === 'delivered') ? 'delivered' : 'pending'
}

/** Самый поздний по времени в пути стоп: остальные сворачиваются в счётчик. */
function latestStop(stops: ClientPlanInfo[]): ClientPlanInfo | null {
  return [...stops].sort((a, b) => b.etaMinutes - a.etaMinutes)[0] ?? null
}

/** Точки карты: склады + клиенты с их заявками, статусом и данными плана. */
export function buildMapPoints(
  warehouses: Warehouse[],
  clients: Client[],
  orders: ClientOrder[],
  products: Product[] = [],
  planByOrder: Map<number, ClientPlanInfo[]> = new Map(),
): MapPoint[] {
  const productNames = new Map(products.map((product) => [product.id, product.name]))

  const points: MapPoint[] = warehouses.map((warehouse) => ({
    id: `warehouse-${warehouse.id}`,
    kind: 'warehouse',
    name: warehouse.name,
    address: warehouse.address,
    coordinates: [warehouse.lon, warehouse.lat],
    roadType: null,
    deliveryStatus: null,
    orderCount: 0,
    requestedKg: 0,
    orders: [],
    plan: null,
    planStopsCount: 0,
  }))

  for (const client of clients) {
    const own = orders.filter((order) => order.client_id === client.id)
    const ownOrders: MapPointOrder[] = own.map((order) => {
      const stops = planByOrder.get(order.id) ?? []
      return {
        orderId: order.id,
        productName: productNames.get(order.product_id) ?? 'Урожай',
        requestedKg: order.requested_kg,
        purchasePriceRub: order.purchase_price_rub,
        deliveredKg: order.delivered_kg,
        deliveryStatus: order.delivery_status,
        plan: latestStop(stops),
        planStopsCount: stops.length,
      }
    })
    const planned = ownOrders.flatMap((order) => (order.plan ? [order.plan] : []))

    points.push({
      id: `client-${client.id}`,
      kind: 'client',
      name: client.name,
      address: client.address,
      coordinates: [client.lon, client.lat],
      roadType: client.road_type,
      deliveryStatus: clientStatus(own),
      orderCount: own.length,
      requestedKg: own.reduce((sum, order) => sum + order.requested_kg, 0),
      orders: ownOrders,
      plan: latestStop(planned),
      planStopsCount: planned.length,
    })
  }

  return points
}

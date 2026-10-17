/**
 * Маркеры и слои карты Калужской области (Day 5).
 *
 * Маркеры создаются как DOM-элементы (кнопки) с текстовыми aria-label и popup,
 * поэтому тип дороги и статус доставки передаются не только цветом.
 */

import mapboxgl from 'mapbox-gl'
import type {
  Client,
  ClientOrder,
  DeliveryStatus,
  RoadType,
  Route,
  Warehouse,
} from '@/shared/types/domain'

/** Центр Калужской области — склад в Обнинске. */
export const OBNINSK_CENTER: [number, number] = [36.6103, 55.0968]
export const DEFAULT_ZOOM = 8.6

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

/** Точки карты: склады + клиенты с агрегированным статусом их заявок. */
export function buildMapPoints(
  warehouses: Warehouse[],
  clients: Client[],
  orders: ClientOrder[],
): MapPoint[] {
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
  }))

  for (const client of clients) {
    const own = orders.filter((order) => order.client_id === client.id)
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
    })
  }

  return points
}

function escapeHtml(value: string): string {
  return value
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
}

export function markerIcon(point: MapPoint): string {
  if (point.kind === 'warehouse') return 'mdi-warehouse'
  return point.roadType === 'dirt' ? 'mdi-road-variant' : 'mdi-storefront-outline'
}

export function markerLabel(point: MapPoint): string {
  const parts = [point.kind === 'warehouse' ? 'Склад' : 'Клиент', point.name]
  if (point.roadType) parts.push(roadLabel(point.roadType))
  if (point.deliveryStatus) parts.push(statusLabel(point.deliveryStatus))
  return parts.join(', ')
}

const MARKER_MODIFIER_PREFIX = 'map-marker--'

/** Наши классы состояния (вид точки, тип дороги, статус). */
function markerModifiers(point: MapPoint): string[] {
  return [
    `map-marker--${point.kind}`,
    point.roadType ? `map-marker--${point.roadType}` : '',
    point.deliveryStatus ? `map-marker--${point.deliveryStatus}` : '',
  ].filter(Boolean)
}

/**
 * Пересобирает только собственные модификаторы маркера.
 * Служебные классы Mapbox (mapboxgl-marker, mapboxgl-marker-anchor-*) трогать
 * нельзя: именно они задают position: absolute и will-change: transform — без них
 * маркер выпадает из слоя карты и перестаёт двигаться вместе с ней.
 */
function applyModifiers(element: HTMLElement, point: MapPoint): void {
  for (const className of [...element.classList]) {
    if (className.startsWith(MARKER_MODIFIER_PREFIX)) element.classList.remove(className)
  }
  element.classList.add('map-marker', ...markerModifiers(point))
}

export function createMarkerElement(point: MapPoint): HTMLButtonElement {
  const element = document.createElement('button')
  element.type = 'button'
  element.classList.add(...markerModifiers(point))
  element.classList.add('map-marker')
  element.setAttribute('aria-label', markerLabel(point))
  element.title = markerLabel(point)
  element.innerHTML = `<span class="mdi ${markerIcon(point)}" aria-hidden="true"></span>`
  return element
}

export function popupHtml(point: MapPoint): string {
  const rows: string[] = []
  if (point.address) rows.push(`<div class="map-popup__row">${escapeHtml(point.address)}</div>`)
  if (point.roadType)
    rows.push(
      `<div class="map-popup__row">Подъезд: <strong>${roadLabel(point.roadType)}</strong></div>`,
    )
  if (point.deliveryStatus)
    rows.push(
      `<div class="map-popup__row">Статус: <strong>${statusLabel(point.deliveryStatus)}</strong></div>`,
    )
  if (point.orderCount > 0)
    rows.push(
      `<div class="map-popup__row">Заявок: ${point.orderCount} · ${Math.round(point.requestedKg)} кг</div>`,
    )

  return `<div class="map-popup"><strong>${escapeHtml(point.name)}</strong>${rows.join('')}</div>`
}

/** Ручка маркера, которую нужно обновить после свежих данных с сервера. */
export interface MarkerHandle {
  point: MapPoint
  element: HTMLButtonElement
  popup: mapboxgl.Popup
}

/** Обновляет подпись, цветовые классы и содержимое popup по свежей точке. */
export function applyPoint(handle: MarkerHandle, point: MapPoint): void {
  handle.point = point
  applyModifiers(handle.element, point)
  handle.element.setAttribute('aria-label', markerLabel(point))
  handle.element.title = markerLabel(point)
  handle.element.innerHTML = `<span class="mdi ${markerIcon(point)}" aria-hidden="true"></span>`
  handle.popup.setHTML(popupHtml(point))
}

export interface MarkerManagerOptions {
  /** Вызывается при наведении: точка, текущие данные и ручка для обновления. */
  onHover?: (handle: MarkerHandle) => void
}

export interface MarkerManager {
  /** Пересоздаёт маркеры (первый рендер, reset-demo). */
  sync(points: MapPoint[]): void
  /** Обновляет подписи и popup без пересоздания: открытый popup не теряется. */
  applyAll(points: MapPoint[]): void
  destroy(): void
}

export function createMarkerManager(
  map: mapboxgl.Map,
  options: MarkerManagerOptions = {},
): MarkerManager {
  let markers: mapboxgl.Marker[] = []
  let handles: MarkerHandle[] = []
  let activePopup: mapboxgl.Popup | null = null

  const syncRef = (points: MapPoint[]): void => {
    for (const marker of markers) marker.remove()
    if (activePopup) {
      activePopup.remove()
      activePopup = null
    }

    const fresh: MarkerHandle[] = []
    markers = points.map((point) => {
      const element = createMarkerElement(point)
      const popup = new mapboxgl.Popup({ offset: 26, closeButton: false }).setHTML(popupHtml(point))
      const marker = new mapboxgl.Marker({ element, anchor: 'bottom' })
        .setLngLat(point.coordinates)
        .setPopup(popup)
        .addTo(map)

      const handle: MarkerHandle = { point, element, popup }
      fresh.push(handle)

      element.addEventListener('mouseenter', () => {
        if (activePopup && activePopup !== popup) activePopup.remove()
        activePopup = popup
        marker.togglePopup()
        options.onHover?.(handle)
      })
      element.addEventListener('focus', () => options.onHover?.(handle))
      return marker
    })
    handles = fresh
  }

  return {
    sync: syncRef,
    applyAll(points: MapPoint[]): void {
      const sameSet =
        points.length === handles.length &&
        points.every((point) => handles.some((handle) => handle.point.id === point.id))
      if (!sameSet) {
        syncRef(points)
        return
      }
      for (const handle of handles) {
        const fresh = points.find((point) => point.id === handle.point.id)
        if (fresh) applyPoint(handle, fresh)
      }
    },
    destroy(): void {
      for (const marker of markers) marker.remove()
      markers = []
      handles = []
      if (activePopup) {
        activePopup.remove()
        activePopup = null
      }
    },
  }
}

export const ROUTE_SOURCE_ID = 'route-lines'
export const ROUTE_LAYER_ID = 'route-lines-layer'

/** Заглушка под полилинии рейсов: пустой источник и слой создаются заранее. */
export function ensureRouteLayers(map: mapboxgl.Map): void {
  if (!map.getSource(ROUTE_SOURCE_ID)) {
    map.addSource(ROUTE_SOURCE_ID, {
      type: 'geojson',
      data: { type: 'FeatureCollection', features: [] },
    })
  }
  if (!map.getLayer(ROUTE_LAYER_ID)) {
    map.addLayer({
      id: ROUTE_LAYER_ID,
      type: 'line',
      source: ROUTE_SOURCE_ID,
      layout: { 'line-join': 'round', 'line-cap': 'round' },
      paint: {
        'line-color': '#6d28d9',
        'line-width': 3,
        'line-opacity': 0.75,
      },
    })
  }
}

/** Геометрия из SolverResponse: на Day 7–8 сюда придут реальные рейсы. */
export function setRouteGeometry(map: mapboxgl.Map, routes: Route[]): void {
  const source = map.getSource(ROUTE_SOURCE_ID) as mapboxgl.GeoJSONSource | undefined
  if (!source) return
  source.setData({
    type: 'FeatureCollection',
    features: routes.map((route, index) => ({
      type: 'Feature',
      properties: { truck_id: route.truck_id, order: index },
      geometry: {
        type: 'LineString',
        coordinates: route.geometry.map((point) => [point.lon, point.lat] as [number, number]),
      },
    })),
  })
}

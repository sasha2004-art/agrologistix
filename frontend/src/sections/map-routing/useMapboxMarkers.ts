/**
 * Маркеры и слои карты Калужской области (Day 5).
 *
 * Маркеры создаются как DOM-элементы (кнопки) с текстовыми aria-label и popup,
 * поэтому тип точки и статус доставки передаются не только цветом. Наведение
 * показывает краткую подсказку, клик — полную карточку точки: сборка данных
 * лежит в `mapPoints.ts`, разметка карточек — в `mapPopupContent.ts`.
 */

import mapboxgl from 'mapbox-gl'
import { bindOrderToggles, hoverHtml, popupHtml, restoreOrderState } from './mapPopupContent'
import { roadLabel, statusLabel, type MapPoint } from './mapPoints'
import type { Route } from '@/shared/types/domain'

export { buildMapPoints } from './mapPoints'
export type { ClientPlanInfo, MapPoint, MapPointOrder } from './mapPoints'

/** Центр Калужской области — склад в Обнинске. */
export const OBNINSK_CENTER: [number, number] = [36.6103, 55.0968]
export const DEFAULT_ZOOM = 8.6

export function markerIcon(point: MapPoint): string {
  if (point.kind === 'warehouse') return 'mdi-warehouse'
  return point.roadType === 'dirt' ? 'mdi-road-variant' : 'mdi-storefront-outline'
}

export function markerLabel(point: MapPoint): string {
  const parts = [point.kind === 'warehouse' ? 'Склад' : 'Покупатель', point.name]
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
  // Собственная подсказка при наведении заменяет нативный title,
  // иначе браузер показывал бы вторую, всплывающую с задержкой.
  element.removeAttribute('title')
  element.innerHTML = `<span class="mdi ${markerIcon(point)}" aria-hidden="true"></span>`
  return element
}

/** Ручка маркера, которую нужно обновить после свежих данных с сервера. */
export interface MarkerHandle {
  point: MapPoint
  element: HTMLButtonElement
  popup: mapboxgl.Popup
  /** Раскрытые пользователем подробности заявок: переживают перерисовку popup. */
  expandedOrders: Set<number>
}

/** Обновляет подпись, цветовые классы и содержимое popup по свежей точке. */
export function applyPoint(handle: MarkerHandle, point: MapPoint): void {
  handle.point = point
  applyModifiers(handle.element, point)
  handle.element.setAttribute('aria-label', markerLabel(point))
  handle.element.removeAttribute('title')
  handle.element.innerHTML = `<span class="mdi ${markerIcon(point)}" aria-hidden="true"></span>`
  handle.popup.setHTML(popupHtml(point))
  // Разметка пересобрана: возвращаем раскрытые заявки, иначе они закрывались бы
  // при каждом фоновом обновлении ERP раз в секунду.
  restoreOrderState(handle.popup.getElement(), handle.expandedOrders)
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
  // Одна общая подсказка на карту: при наведении переезжает к активной точке.
  const hoverTip = new mapboxgl.Popup({
    offset: 26,
    closeButton: false,
    closeOnClick: false,
    className: 'map-hover-tip',
  })

  const showHoverTip = (point: MapPoint): void => {
    hoverTip.setLngLat(point.coordinates).setHTML(hoverHtml(point))
    if (!hoverTip.isOpen()) hoverTip.addTo(map)
  }
  const hideHoverTip = (): void => {
    hoverTip.remove()
  }

  const syncRef = (points: MapPoint[]): void => {
    for (const marker of markers) marker.remove()
    hideHoverTip()
    if (activePopup) {
      activePopup.remove()
      activePopup = null
    }

    const fresh: MarkerHandle[] = []
    markers = points.map((point) => {
      const element = createMarkerElement(point)
      const expandedOrders = new Set<number>()
      const popup = new mapboxgl.Popup({ offset: 26, closeButton: false }).setHTML(popupHtml(point))
      // Кнопки заявок живут внутри popup: клики обрабатываются делегированием.
      bindOrderToggles(popup, expandedOrders)
      const marker = new mapboxgl.Marker({ element, anchor: 'bottom' })
        .setLngLat(point.coordinates)
        .setPopup(popup)
        .addTo(map)

      const handle: MarkerHandle = { point, element, popup, expandedOrders }
      fresh.push(handle)

      element.addEventListener('mouseenter', () => {
        options.onHover?.(handle)
        // Если полная карточка уже открыта кликом, подсказка только дублировала бы её.
        if (popup.isOpen()) return
        showHoverTip(handle.point)
      })
      element.addEventListener('mouseleave', hideHoverTip)
      element.addEventListener('click', () => {
        hideHoverTip()
        if (activePopup && activePopup !== popup) activePopup.remove()
        activePopup = popup
      })
      element.addEventListener('focus', () => {
        options.onHover?.(handle)
        if (!popup.isOpen()) showHoverTip(handle.point)
      })
      element.addEventListener('blur', hideHoverTip)
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
      hideHoverTip()
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
        // Цвет рейса приходит свойством GeoJSON-фичи: у каждой машины свой оттенок.
        'line-color': ['get', 'color'],
        'line-width': ['case', ['get', 'highlight'], 5, 3.5],
        'line-opacity': 0.8,
      },
    })
  }
}

/** Геометрия рейсов из `SolverResponse`: одна линия на машину, цвет — из палитры UI. */
export function setRouteGeometry(
  map: mapboxgl.Map,
  routes: Route[],
  colorOf: (truckId: number, index: number) => string = () => '#6d28d9',
  highlightTruckId: number | null = null,
): void {
  const source = map.getSource(ROUTE_SOURCE_ID) as mapboxgl.GeoJSONSource | undefined
  if (!source) return
  source.setData({
    type: 'FeatureCollection',
    features: routes
      .filter((route) => route.geometry.length > 1)
      .map((route, index) => ({
        type: 'Feature' as const,
        properties: {
          truck_id: route.truck_id,
          truck_name: route.truck_name,
          color: colorOf(route.truck_id, index),
          highlight: highlightTruckId === route.truck_id,
        },
        geometry: {
          type: 'LineString' as const,
          coordinates: route.geometry.map((point) => [point.lon, point.lat] as [number, number]),
        },
      })),
  })
}

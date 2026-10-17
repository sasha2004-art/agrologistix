/**
 * Маркеры и слои карты Калужской области (Day 5).
 *
 * Маркеры создаются как DOM-элементы (кнопки) с текстовыми aria-label и popup,
 * поэтому тип точки и статус доставки передаются не только цветом. Карточка
 * объекта выпадает при наведении на маркер (и при фокусе с клавиатуры), а
 * нажатие закрепляет её: сборка данных лежит в `mapPoints.ts`, разметка
 * карточки — в `mapPopupContent.ts`.
 */

import mapboxgl from 'mapbox-gl'
import { bindOrderToggles, popupHtml, restoreOrderState } from './mapPopupContent'
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
  // Нативный title убран: карточка уже выпадает при наведении, а браузерная
  // подсказка всплывала бы с задержкой и дублировала aria-label.
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

export interface MarkerManager {
  /** Пересоздаёт маркеры (первый рендер, reset-demo). */
  sync(points: MapPoint[]): void
  /** Обновляет подписи и popup без пересоздания: открытый popup не теряется. */
  applyAll(points: MapPoint[]): void
  destroy(): void
}

/** Пауза перед закрытием карточки: курсор успевает перейти с маркера в неё. */
const POPUP_CLOSE_DELAY_MS = 180

export function createMarkerManager(map: mapboxgl.Map): MarkerManager {
  let markers: mapboxgl.Marker[] = []
  let handles: MarkerHandle[] = []
  let activePopup: mapboxgl.Popup | null = null
  /** Карточка, закреплённая нажатием: не закрывается при уходе курсора. */
  let pinnedPopup: mapboxgl.Popup | null = null
  let closeTimer: ReturnType<typeof setTimeout> | null = null

  const cancelClose = (): void => {
    if (closeTimer === null) return
    clearTimeout(closeTimer)
    closeTimer = null
  }

  const openPopup = (handle: MarkerHandle): void => {
    cancelClose()
    if (activePopup && activePopup !== handle.popup) activePopup.remove()
    handle.popup.setLngLat(handle.point.coordinates).addTo(map)
    activePopup = handle.popup
  }

  const closePopup = (popup: mapboxgl.Popup): void => {
    cancelClose()
    if (pinnedPopup === popup) pinnedPopup = null
    if (activePopup === popup) {
      popup.remove()
      activePopup = null
    }
  }

  /** Закрывает карточку после паузы, если её не закрепили нажатием. */
  const scheduleClose = (handle: MarkerHandle): void => {
    if (pinnedPopup === handle.popup) return
    cancelClose()
    closeTimer = setTimeout(() => {
      closeTimer = null
      if (pinnedPopup === handle.popup) return
      if (activePopup === handle.popup) {
        handle.popup.remove()
        activePopup = null
      }
    }, POPUP_CLOSE_DELAY_MS)
  }

  /**
   * Карточка выпадает по наведению и фокусу, а нажатие её закрепляет. Внутри
   * карточки список заказов тоже раскрывается по наведению; клики по строкам
   * обрабатываются делегированием на контейнер popup.
   */
  const bindHoverTriggers = (handle: MarkerHandle): void => {
    const { element, popup } = handle

    element.addEventListener('mouseenter', () => openPopup(handle))
    element.addEventListener('mouseleave', () => scheduleClose(handle))
    element.addEventListener('focusin', () => openPopup(handle))
    element.addEventListener('focusout', () => scheduleClose(handle))
    element.addEventListener('click', () => {
      if (pinnedPopup === popup) closePopup(popup)
      else {
        pinnedPopup = popup
        openPopup(handle)
      }
    })

    // Контейнер popup создаётся при первом показе и живёт до закрытия, поэтому
    // обработчики содержимого навешиваются при каждом открытии.
    popup.on('open', () => {
      const container = popup.getElement()
      if (!container) return
      bindOrderToggles(popup, handle.expandedOrders)
      restoreOrderState(container, handle.expandedOrders)
      if (container.dataset.hoverBound === 'true') return
      container.dataset.hoverBound = 'true'
      container.addEventListener('mouseenter', cancelClose)
      container.addEventListener('mouseleave', () => scheduleClose(handle))
      container.addEventListener('focusin', cancelClose)
      container.addEventListener('focusout', () => scheduleClose(handle))
    })
  }

  const syncRef = (points: MapPoint[]): void => {
    for (const marker of markers) marker.remove()
    if (activePopup) {
      activePopup.remove()
      activePopup = null
    }
    pinnedPopup = null
    cancelClose()

    const fresh: MarkerHandle[] = []
    markers = points.map((point) => {
      const element = createMarkerElement(point)
      const expandedOrders = new Set<number>()
      const popup = new mapboxgl.Popup({
        offset: 26,
        closeButton: false,
        // Наведение не должно перетаскивать фокус на карточку.
        focusAfterOpen: false,
      }).setHTML(popupHtml(point))
      popup.on('close', () => {
        if (pinnedPopup === popup) pinnedPopup = null
        if (activePopup === popup) activePopup = null
      })
      const marker = new mapboxgl.Marker({ element, anchor: 'bottom' })
        .setLngLat(point.coordinates)
        .addTo(map)

      const handle: MarkerHandle = { point, element, popup, expandedOrders }
      fresh.push(handle)
      bindHoverTriggers(handle)
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
      cancelClose()
      pinnedPopup = null
      if (activePopup) {
        activePopup.remove()
        activePopup = null
      }
    },
  }
}

export const FIXED_SOURCE_ID = 'fixed-routes'
export const FIXED_LAYER_ID = 'fixed-routes-layer'
/** Цвет пунктирных линий зафиксированных рейсов. */
export const FIXED_ROUTE_COLOR = '#0f766e'

/**
 * Пунктирный слой фиксированных рейсов: заявки «В работе» держат ссылку на
 * выбранную машину и маршрут, поэтому линии видны сразу после подбора.
 */
export function ensureFixedRouteLayers(map: mapboxgl.Map): void {
  if (!map.getSource(FIXED_SOURCE_ID)) {
    map.addSource(FIXED_SOURCE_ID, {
      type: 'geojson',
      data: { type: 'FeatureCollection', features: [] },
    })
  }
  if (!map.getLayer(FIXED_LAYER_ID)) {
    map.addLayer({
      id: FIXED_LAYER_ID,
      type: 'line',
      source: FIXED_SOURCE_ID,
      layout: { 'line-join': 'round', 'line-cap': 'round' },
      paint: {
        'line-color': FIXED_ROUTE_COLOR,
        'line-width': 3,
        'line-opacity': 0.85,
        // Пунктир отличает фиксированный рейс от полилиний рассчитанного плана.
        'line-dasharray': [2, 1.5],
      },
    })
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

/** Геометрия фиксированных маршрутов: по пунктирной линии на каждую заявку. */
export function setFixedRouteGeometry(
  map: mapboxgl.Map,
  assignments: { order_id: number; truck_name: string; geometry: { lat: number; lon: number }[] }[],
): void {
  const source = map.getSource(FIXED_SOURCE_ID) as mapboxgl.GeoJSONSource | undefined
  if (!source) return
  source.setData({
    type: 'FeatureCollection',
    features: assignments
      .filter((item) => item.geometry.length > 1)
      .map((item) => ({
        type: 'Feature' as const,
        properties: { order_id: item.order_id, truck_name: item.truck_name },
        geometry: {
          type: 'LineString' as const,
          coordinates: item.geometry.map((point) => [point.lon, point.lat] as [number, number]),
        },
      })),
  })
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

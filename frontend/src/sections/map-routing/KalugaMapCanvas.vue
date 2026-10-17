<template>
  <section class="map-panel soft-card" aria-label="Карта Калужской области">
    <header class="map-header">
      <div>
        <h2 class="map-title">Карта Калужской области</h2>
      </div>
    </header>

    <div class="map-area">
      <div
        v-if="showMap"
        ref="container"
        class="map-canvas"
        :class="{ 'map-canvas--dimmed': !mapReady }"
        aria-label="Интерактивная карта складов и покупателей"
      />
      <MapFallbackPanel v-else :reason="fallbackReason" />

      <div v-if="showMap && !mapReady" class="map-overlay" role="status" aria-live="polite">
        <v-progress-circular indeterminate size="22" width="2" color="primary" />
        <span>Загружаем карту…</span>
      </div>
      <!-- Легенда — постоянный оверлей поверх карты. -->
      <MapLegend :schedule="solver.routeLegend" :has-fixed-routes="hasFixedRoutes" />
    </div>
  </section>
</template>

<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import mapboxgl from 'mapbox-gl'
import 'mapbox-gl/dist/mapbox-gl.css'
import MapFallbackPanel from './MapFallbackPanel.vue'
import MapLegend from './MapLegend.vue'
import {
  DEFAULT_ZOOM,
  OBNINSK_CENTER,
  buildMapPoints,
  createMarkerManager,
  ensureFixedRouteLayers,
  ensureRouteLayers,
  setFixedRouteGeometry,
  setRouteGeometry,
  type MapPoint,
  type MarkerManager,
} from './useMapboxMarkers'
import { useAssignmentStore } from '@/sections/erp-dashboard/useAssignmentStore'
import { useErpStore } from '@/sections/erp-dashboard/useErpStore'
import { useSolverStore } from '@/sections/erp-dashboard/useSolverStore'
import type { ClientPlanInfo } from './useMapboxMarkers'
import { routeColor } from '@/shared/utils/routeColors'
import type { Route } from '@/shared/types/domain'

const props = withDefaults(defineProps<{ routes?: Route[] }>(), { routes: () => [] })

const erp = useErpStore()
const solver = useSolverStore()
const assignments = useAssignmentStore()
const container = ref<HTMLDivElement | null>(null)
const mapReady = ref(false)
const mapFailed = ref(false)
const failureText = ref<string | null>(null)

const accessToken = (import.meta.env.VITE_MAPBOX_PUBLIC_TOKEN ?? '').trim()

/**
 * Данные плана по заявке: карточка заказа показывает рейс, ETA, свежесть и вес.
 * Одна заявка может дробиться между рейсами, поэтому стопов может быть несколько.
 */
const planByOrder = computed(() => {
  const map = new Map<number, ClientPlanInfo[]>()
  for (const item of solver.plannedStops) {
    if (item.stop.order_id == null) continue
    const stops = map.get(item.stop.order_id) ?? []
    stops.push({
      orderId: item.stop.order_id,
      truckName: item.truckName,
      color: item.color,
      etaMinutes: item.stop.eta_minutes,
      expectedFreshness: item.stop.expected_freshness,
      shippedKg: item.stop.shipped_kg,
      sequenceOrder: item.stop.sequence_order,
      distanceKm: item.stop.distance_km,
      tripLegCostRub: item.stop.trip_leg_cost_rub,
    })
    map.set(item.stop.order_id, stops)
  }
  return map
})

const points = computed<MapPoint[]>(() =>
  buildMapPoints(erp.warehouses, erp.clients, erp.orders, erp.products, planByOrder.value),
)
const fixedAssignments = computed(() => Object.values(assignments.assignments))
const hasFixedRoutes = computed(() =>
  fixedAssignments.value.some((item) => item.geometry.length > 1),
)
const showMap = computed(() => accessToken.length > 0 && !mapFailed.value)
const fallbackReason = computed(() => {
  if (!accessToken) return 'Карта недоступна — показываем список складов и покупателей.'
  return failureText.value ?? 'Карта недоступна — показываем список складов и покупателей.'
})

let map: mapboxgl.Map | null = null
let markers: MarkerManager | null = null
/** Уже показанные фиксации: по ним понимаем, какая появилась только что. */
let knownFixedIds = new Set<number>()

function teardownMap(): void {
  markers?.destroy()
  markers = null
  map?.remove()
  map = null
  mapReady.value = false
}

function failWith(message: string): void {
  failureText.value = message
  teardownMap()
  mapFailed.value = true
}

onMounted(() => {
  if (!showMap.value) return
  mapboxgl.accessToken = accessToken
  try {
    map = new mapboxgl.Map({
      container: container.value as HTMLElement,
      style: 'mapbox://styles/mapbox/light-v11',
      center: OBNINSK_CENTER,
      zoom: DEFAULT_ZOOM,
      // Подпись Mapbox обязательна по лицензии, компактный вид не мешает карте.
      attributionControl: false,
    })
  } catch (error) {
    failWith(
      `Не удалось инициализировать карту: ${error instanceof Error ? error.message : 'неизвестная ошибка'}`,
    )
    return
  }

  // Контролы разведены по углам: ничего не липнет к скруглённым краям карты.
  map.addControl(new mapboxgl.NavigationControl({ showCompass: false }), 'top-right')
  map.addControl(new mapboxgl.ScaleControl({ maxWidth: 90, unit: 'metric' }), 'bottom-right')

  map.on('load', () => {
    if (!map) return
    mapReady.value = true
    applySerenityPalette(map)
    ensureRouteLayers(map)
    ensureFixedRouteLayers(map)
    markers = createMarkerManager(map)
    markers.sync(points.value)
    drawRoutes()
    drawFixedRoutes()
    // Начальные фиксации (гидратация из ERP) не двигают карту.
    knownFixedIds = new Set(Object.keys(assignments.assignments).map(Number))
  })

  map.on('error', (event) => {
    // Критична только ошибка до первой загрузки: после неё маркеры и ER-данные важнее тайлов.
    if (mapReady.value) {
      console.warn('[map] Mapbox error', event.error)
      return
    }
    failWith(`Mapbox недоступен: ${event.error?.message ?? 'ошибка загрузки стиля'}`)
  })
})

watch(
  points,
  (next) => {
    if (mapReady.value) markers?.applyAll(next)
  },
  { deep: true },
)

/**
 * Мягкая палитра проекта: вода и фон в тонах «Serenity» вместо холодного серого.
 * Слои стиля могут отличаться, поэтому каждый цвет применяется отдельно и безопасно.
 */
function applySerenityPalette(target: mapboxgl.Map): void {
  const palette = [
    { layer: 'background', property: 'background-color' as const, color: '#f6f2fd' },
    { layer: 'water', property: 'fill-color' as const, color: '#dcd0f4' },
    { layer: 'waterway', property: 'line-color' as const, color: '#c9b6ee' },
  ]
  for (const { layer, property, color } of palette) {
    if (!target.getLayer(layer)) continue
    try {
      target.setPaintProperty(layer, property, color)
    } catch {
      /* слой есть, но свойство другое — оставляем стиль как есть */
    }
  }
}

/** Рисует полилинии рейсов цветами палитры, совпадающими с таблицей плана. */
function drawRoutes(): void {
  if (!map) return
  setRouteGeometry(map, props.routes ?? [], (_truckId, index) => routeColor(index))
}

/** Пунктирные линии фиксированных маршрутов заявок «В работе». */
function drawFixedRoutes(): void {
  if (!map) return
  setFixedRouteGeometry(map, fixedAssignments.value)
}

/** Карта подлетает к маршруту, который только что зафиксировали. */
function focusFixedRoute(geometry: { lat: number; lon: number }[]): void {
  if (!map || geometry.length < 2) return
  const bounds = new mapboxgl.LngLatBounds()
  for (const point of geometry) bounds.extend([point.lon, point.lat])
  map.fitBounds(bounds, { padding: 90, duration: 700, maxZoom: 10 })
}

watch(
  () => props.routes,
  () => {
    if (mapReady.value) drawRoutes()
  },
  { deep: true },
)

watch(
  () => assignments.assignments,
  (next) => {
    if (!mapReady.value) return
    drawFixedRoutes()
    const ids = new Set(Object.keys(next).map(Number))
    const added = [...ids].filter((id) => !knownFixedIds.has(id))
    knownFixedIds = ids
    // Зумим только к одиночной новой фиксации, а не к массовой смене статуса.
    const focused = added.length === 1 ? next[added[0] as number] : undefined
    if (focused) focusFixedRoute(focused.geometry)
  },
  { deep: true },
)

onBeforeUnmount(teardownMap)
</script>

<style scoped lang="scss">
.map-panel {
  display: flex;
  flex-direction: column;
  flex: 1 1 auto;
  min-width: 0;
  min-height: 0;
  padding: 18px;
  overflow: hidden;
}

.map-header {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 12px;
  margin-bottom: 14px;
}

.map-title {
  margin: 0;
  font-size: 18px;
}

.map-area {
  position: relative;
  display: flex;
  flex-direction: column;
  flex: 1 1 auto;
  min-height: 0;
}

.map-canvas {
  flex: 1 1 auto;
  min-height: 220px;
  border: var(--neu-border);
  border-radius: var(--neu-radius);
  box-shadow: var(--neu-lift-sm);
  overflow: hidden;
}

.map-canvas--dimmed {
  opacity: 0.6;
}

.map-overlay {
  position: absolute;
  inset: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 10px;
  font-size: 13px;
  color: #5b5175;
  background: rgba(242, 236, 251, 0.6);
  pointer-events: none;
}

/* Масштабная линейка и подпись Mapbox в той же мягкой палитре, что и панели. */
.map-area :deep(.mapboxgl-ctrl-scale) {
  border: var(--neu-border) !important;
  border-top: none !important;
  border-radius: 0 0 8px 8px;
  background: rgba(247, 244, 254, 0.92) !important;
  color: #4c3f75 !important;
  font-size: 10px;
}
</style>

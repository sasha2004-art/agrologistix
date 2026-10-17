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
    </div>

    <ul v-if="showMap" class="map-legend">
      <li class="legend-item">
        <span class="legend-marker legend-marker--warehouse" aria-hidden="true" />
        Склад
      </li>
      <li class="legend-item">
        <span class="legend-marker legend-marker--asphalt" aria-hidden="true" />
        Покупатель — асфальт
      </li>
      <li class="legend-item">
        <span class="legend-marker legend-marker--dirt" aria-hidden="true" />
        Покупатель — грунтовка
      </li>
      <li class="legend-item">
        <span class="legend-marker legend-marker--pending" aria-hidden="true" />
        Заказ в плане
      </li>
      <li class="legend-item">
        <span class="legend-marker legend-marker--delivered" aria-hidden="true" />
        Доставлено
      </li>
    </ul>

    <ul
      v-if="solver.routes.length > 0"
      class="map-legend map-legend--routes"
      aria-label="Рейсы плана"
    >
      <li v-for="route in solver.routeLegend" :key="route.truckId" class="legend-item">
        <span class="legend-line" :style="{ background: route.color }" aria-hidden="true" />
        {{ route.truckName }}: {{ route.stops }} остановок, {{ formatKm(route.distanceKm) }},
        {{ formatRub(route.costRub) }}
      </li>
    </ul>
  </section>
</template>

<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import mapboxgl from 'mapbox-gl'
import 'mapbox-gl/dist/mapbox-gl.css'
import MapFallbackPanel from './MapFallbackPanel.vue'
import {
  DEFAULT_ZOOM,
  OBNINSK_CENTER,
  buildMapPoints,
  createMarkerManager,
  ensureRouteLayers,
  setRouteGeometry,
  type MapPoint,
  type MarkerManager,
} from './useMapboxMarkers'
import { useErpStore } from '@/sections/erp-dashboard/useErpStore'
import { useSolverStore } from '@/sections/erp-dashboard/useSolverStore'
import type { ClientPlanInfo } from './useMapboxMarkers'
import { routeColor } from '@/shared/utils/routeColors'
import { formatKm, formatRub } from '@/shared/utils/format'
import type { Route } from '@/shared/types/domain'

const props = withDefaults(defineProps<{ routes?: Route[] }>(), { routes: () => [] })

const erp = useErpStore()
const solver = useSolverStore()
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
const showMap = computed(() => accessToken.length > 0 && !mapFailed.value)
const fallbackReason = computed(() => {
  if (!accessToken) return 'Карта недоступна — показываем список складов и покупателей.'
  return failureText.value ?? 'Карта недоступна — показываем список складов и покупателей.'
})

let map: mapboxgl.Map | null = null
let markers: MarkerManager | null = null

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
      attributionControl: false,
    })
  } catch (error) {
    failWith(
      `Не удалось инициализировать карту: ${error instanceof Error ? error.message : 'неизвестная ошибка'}`,
    )
    return
  }

  map.addControl(new mapboxgl.NavigationControl({ showCompass: false }), 'top-right')

  map.on('load', () => {
    if (!map) return
    mapReady.value = true
    ensureRouteLayers(map)
    markers = createMarkerManager(map)
    markers.sync(points.value)
    drawRoutes()
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

/** Рисует полилинии рейсов цветами палитры, совпадающими с таблицей плана. */
function drawRoutes(): void {
  if (!map) return
  setRouteGeometry(map, props.routes ?? [], (_truckId, index) => routeColor(index))
}

watch(
  () => props.routes,
  () => {
    if (mapReady.value) drawRoutes()
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
  border-radius: var(--neu-radius-sm);
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

.map-legend {
  display: flex;
  flex-wrap: wrap;
  gap: 8px 16px;
  margin: 12px 0 0;
  padding: 0;
  list-style: none;
  font-size: 12px;
  color: #5b5175;
}

.legend-item {
  display: inline-flex;
  align-items: center;
  gap: 6px;
}

.legend-marker {
  width: 14px;
  height: 14px;
  border: 2px solid #fff;
  border-radius: 50% 50% 50% 3px;
  background: #5b21b6;
  box-shadow: 0 1px 3px rgba(46, 16, 101, 0.35);
}

.legend-marker--asphalt {
  background: #047857;
}

.legend-marker--dirt {
  background: #b45309;
}

.legend-marker--pending {
  border-radius: 50%;
  background: #e7dff6;
  border-color: #f59e0b;
}

.legend-marker--delivered {
  border-radius: 50%;
  background: #e7dff6;
  border-color: #34d399;
}

/* Легенда рейсов: цвет линии совпадает с полилинией на карте и таблицей плана. */
.map-legend--routes {
  padding-top: 8px;
  border-top: 1px dashed rgba(91, 81, 117, 0.3);
}

.legend-line {
  flex: 0 0 auto;
  width: 22px;
  height: 4px;
  border-radius: 2px;
}
</style>

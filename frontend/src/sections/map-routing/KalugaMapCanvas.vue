<template>
  <section class="map-panel soft-card" aria-label="Карта Калужской области">
    <header class="map-header">
      <div>
        <h2 class="map-title">Карта Калужской области</h2>
        <p class="map-subtitle">
          Центр — Обнинск, {{ OBNINSK_CENTER[1].toFixed(4) }} / {{ OBNINSK_CENTER[0].toFixed(4) }}.
          {{ mapReady ? 'Клик по маркеру — детали точки.' : 'Карта в режиме схемы.' }}
        </p>
      </div>
    </header>

    <div class="map-area">
      <div
        v-if="showMap"
        ref="container"
        class="map-canvas"
        :class="{ 'map-canvas--dimmed': !mapReady }"
        aria-label="Интерактивная карта складов и клиентов"
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
        Клиент, асфальт
      </li>
      <li class="legend-item">
        <span class="legend-marker legend-marker--dirt" aria-hidden="true" />
        Клиент, грунтовка
      </li>
      <li class="legend-item">
        <span class="legend-marker legend-marker--pending" aria-hidden="true" />
        Заявки в работе
      </li>
      <li class="legend-item">
        <span class="legend-marker legend-marker--delivered" aria-hidden="true" />
        Доставлено
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
  applyPoint,
  buildMapPoints,
  createMarkerManager,
  ensureRouteLayers,
  setRouteGeometry,
  type MapPoint,
  type MarkerHandle,
  type MarkerManager,
} from './useMapboxMarkers'
import { useErpStore } from '@/sections/erp-dashboard/useErpStore'
import type { Route } from '@/shared/types/domain'

const props = withDefaults(defineProps<{ routes?: Route[] }>(), { routes: () => [] })

const erp = useErpStore()
const container = ref<HTMLDivElement | null>(null)
const mapReady = ref(false)
const mapFailed = ref(false)
const failureText = ref<string | null>(null)

const accessToken = (import.meta.env.VITE_MAPBOX_PUBLIC_TOKEN ?? '').trim()
const points = computed<MapPoint[]>(() => buildMapPoints(erp.warehouses, erp.clients, erp.orders))
const showMap = computed(() => accessToken.length > 0 && !mapFailed.value)
const fallbackReason = computed(() => {
  if (!accessToken)
    return 'Не задан VITE_MAPBOX_PUBLIC_TOKEN: показываем схему точек. Интерактивная карта включится после сборки с токеном.'
  return failureText.value ?? 'Mapbox недоступен: показываем схему точек.'
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
    markers = createMarkerManager(map, {
      onHover: handleMarkerHover,
    })
    markers.sync(points.value)
    setRouteGeometry(map, props.routes ?? [])
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

/**
 * Маркеры живут только от общего стора: наведение просто дорисовывает актуальную
 * точку (сеть тянет фоновый опрос раз в секунду в useErpStore.startAutoSync).
 */
function handleMarkerHover(handle: MarkerHandle): void {
  const fresh = points.value.find((point) => point.id === handle.point.id)
  if (fresh) applyPoint(handle, fresh)
}

watch(
  points,
  (next) => {
    if (mapReady.value) markers?.applyAll(next)
  },
  { deep: true },
)

watch(
  () => props.routes,
  (next) => {
    if (mapReady.value && map) setRouteGeometry(map, next ?? [])
  },
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

.map-subtitle {
  margin: 4px 0 0;
  font-size: 13px;
  color: #5b5175;
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
</style>

<template>
  <aside class="legend" aria-label="Обозначения на карте">
    <div class="legend-group">
      <p class="legend-group-title">Точки</p>
      <ul class="legend-list legend-list--row">
        <li v-for="item in pointLegend" :key="item.key" class="legend-item">
          <span class="legend-marker" :class="item.markerClass" aria-hidden="true" />
          {{ item.label }}
        </li>
      </ul>
    </div>

    <div class="legend-group">
      <p class="legend-group-title">Рейсы</p>
      <!-- Блок не исчезает: без расчёта он показывает причину, поэтому легенда не «мигает». -->
      <p v-if="!hasRoutes" class="legend-empty">Маршрут ещё не рассчитан</p>
      <ul v-else class="legend-list legend-list--row">
        <li v-for="route in schedule" :key="route.truckId" class="legend-item legend-item--route">
          <span class="legend-line" :style="{ background: route.color }" aria-hidden="true" />
          <span class="legend-route-text">
            <strong>{{ route.truckName }}</strong>
            <span class="legend-route-meta">
              {{ route.stops }} ост. · {{ formatKm(route.distanceKm) }} ·
              {{ formatRub(route.costRub) }}
            </span>
          </span>
        </li>
      </ul>
    </div>
  </aside>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { formatKm, formatRub } from '@/shared/utils/format'

/** Строка легенды по одному рейсу: цвет совпадает с полилинией и таблицей плана. */
export interface RouteLegendItem {
  truckId: number
  truckName: string
  color: string
  stops: number
  distanceKm: number
  costRub: number
}

const props = withDefaults(defineProps<{ schedule?: RouteLegendItem[] }>(), {
  schedule: () => [],
})
const hasRoutes = computed(() => props.schedule.length > 0)

const pointLegend = [
  { key: 'warehouse', label: 'Склад', markerClass: 'legend-marker--warehouse' },
  { key: 'asphalt', label: 'Подъезд: асфальт', markerClass: 'legend-marker--asphalt' },
  { key: 'dirt', label: 'Подъезд: грунтовка', markerClass: 'legend-marker--dirt' },
  { key: 'pending', label: 'Заказ в плане', markerClass: 'legend-marker--pending' },
  { key: 'in_progress', label: 'Заказ в работе', markerClass: 'legend-marker--in_progress' },
  { key: 'delivered', label: 'Доставлено', markerClass: 'legend-marker--delivered' },
]
</script>

<style scoped lang="scss">
/*
 * Компактный квадратный оверлей слева снизу: структура постоянна, поэтому
 * при пересчёте и очистке плана легенда не появляется и не исчезает.
 */
.legend {
  position: absolute;
  bottom: 10px;
  left: 10px;
  z-index: 3;
  display: grid;
  align-content: start;
  gap: 16px;
  /* Базовый компактный блок был ~186×122: теперь шире вдвое, высота — 320 px. */
  width: 372px;
  height: 320px;
  max-width: calc(100% - 20px);
  max-height: calc(100% - 20px);
  padding: 16px 18px;
  overflow-y: auto;
  border: var(--neu-border);
  border-radius: var(--neu-radius-sm);
  background: rgba(247, 244, 254, 0.94);
  box-shadow: 0 10px 26px rgba(46, 16, 101, 0.22);
  backdrop-filter: blur(6px);
  font-size: 13px;
  color: #4c3f75;
}

.legend-group {
  display: grid;
  gap: 6px;
  min-width: 0;
}

.legend-group-title {
  margin: 0;
  font-size: 14px;
  font-weight: 600;
  color: #2e1065;
}

.legend-list {
  display: grid;
  grid-template-columns: 1fr;
  gap: 7px;
  margin: 0;
  padding: 0;
  list-style: none;
}

.legend-item {
  display: flex;
  align-items: center;
  gap: 9px;
  line-height: 1.3;
}

.legend-marker {
  flex: 0 0 auto;
  width: 18px;
  height: 18px;
  border: 2px solid #fff;
  border-radius: 50% 50% 50% 4px;
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
  background: #efe6fb;
  border-color: #f59e0b;
}

.legend-marker--in_progress {
  border-radius: 50%;
  background: #efe6fb;
  border-color: #3b82f6;
}

.legend-marker--delivered {
  border-radius: 50%;
  background: #efe6fb;
  border-color: #34d399;
}

.legend-line {
  flex: 0 0 auto;
  width: 30px;
  height: 5px;
  border-radius: 3px;
}

.legend-route-text {
  display: grid;
  gap: 0;
}

.legend-route-meta {
  color: #5b5175;
}

.legend-route-text strong {
  font-size: 13.5px;
}

.legend-empty {
  margin: 0;
  color: #7c6f9c;
  font-style: italic;
}

.legend-list--row {
  align-items: center;
}
</style>

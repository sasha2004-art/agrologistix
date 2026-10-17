<template>
  <div class="fallback">
    <div class="fallback-canvas neu-inset">
      <div class="fallback-grid" aria-hidden="true" />
      <div class="fallback-content">
        <v-icon icon="mdi-map-search-outline" size="32" color="primary" />
        <p class="fallback-title">Карта недоступна</p>
        <p class="fallback-text">{{ reason }}</p>
      </div>
    </div>

    <StatePanel
      class="fallback-points"
      :status="erp.panelStatus"
      :error-text="erp.errorMessage"
      loading-text="Загружаем склады и покупателей…"
      empty-title="Точек на карте пока нет"
      empty-icon="mdi-map-marker-off-outline"
      @retry="reload"
    >
      <div class="points">
        <div class="points-group">
          <h3 class="points-title">
            <v-icon icon="mdi-warehouse" size="18" color="primary" /> Склады
            <span class="points-count mono">{{ erp.warehouses.length }}</span>
          </h3>
          <ul class="points-list">
            <li v-for="warehouse in erp.warehouses" :key="warehouse.id" class="point">
              <span class="point-name">{{ warehouse.name }}</span>
              <span class="point-coords mono">
                {{ warehouse.lat.toFixed(4) }}, {{ warehouse.lon.toFixed(4) }}
              </span>
            </li>
          </ul>
        </div>

        <div class="points-group">
          <h3 class="points-title">
            <v-icon icon="mdi-storefront-outline" size="18" color="primary" /> Покупатели
            <span class="points-count mono">{{ erp.clients.length }}</span>
          </h3>
          <ul class="points-list">
            <li v-for="client in erp.clients" :key="client.id" class="point">
              <span class="point-name">{{ client.name }}</span>
              <span class="point-meta">
                <v-icon
                  :icon="client.road_type === 'dirt' ? 'mdi-road-variant' : 'mdi-road'"
                  size="14"
                />
                {{ client.road_type === 'dirt' ? 'грунтовка' : 'асфальт' }}
              </span>
            </li>
          </ul>
        </div>
      </div>
    </StatePanel>
  </div>
</template>

<script setup lang="ts">
import StatePanel from '@/shared/components/StatePanel.vue'
import { useErpStore } from '@/sections/erp-dashboard/useErpStore'

withDefaults(
  defineProps<{
    reason?: string
  }>(),
  { reason: 'Показываем список складов и покупателей.' },
)

const erp = useErpStore()

function reload(): void {
  void erp.loadState({ force: true })
}
</script>

<style scoped lang="scss">
.fallback {
  display: flex;
  flex-direction: column;
  min-height: 0;
  overflow-y: auto;
}

.fallback-canvas {
  position: relative;
  display: grid;
  place-items: center;
  min-height: 200px;
  padding: 20px;
  overflow: hidden;
}

.fallback-grid {
  position: absolute;
  inset: 0;
  background-image:
    linear-gradient(rgba(91, 81, 117, 0.12) 1px, transparent 1px),
    linear-gradient(90deg, rgba(91, 81, 117, 0.12) 1px, transparent 1px);
  background-size: 40px 40px;
  pointer-events: none;
}

.fallback-content {
  position: relative;
  display: grid;
  justify-items: center;
  gap: 6px;
  text-align: center;
}

.fallback-title {
  margin: 0;
  font-weight: 600;
}

.fallback-text {
  margin: 0;
  max-width: 460px;
  font-size: 13px;
  color: #5b5175;
}

.points {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(min(240px, 100%), 1fr));
  gap: 14px;
  margin-top: 16px;
}

.points-title {
  display: flex;
  align-items: center;
  gap: 6px;
  margin: 0 0 6px;
  font-size: 14px;
}

.points-count {
  font-size: 12px;
  color: #5b5175;
}

.points-list {
  display: grid;
  gap: 6px;
  margin: 0;
  padding: 0;
  list-style: none;
}

.point {
  display: grid;
  gap: 2px;
  font-size: 13px;
}

.point-name {
  font-weight: 500;
}

.point-meta {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  font-size: 12px;
  color: #5b5175;
}

.point-coords {
  font-size: 12px;
  color: #5b5175;
}
</style>

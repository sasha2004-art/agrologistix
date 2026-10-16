<template>
  <section class="map-panel soft-card" aria-label="Область карты Калужской области">
    <header class="map-header">
      <div>
        <h2 class="map-title">Карта Калужской области</h2>
        <p class="map-subtitle">
          Центр — Обнинск, 55.11 / 36.61. Полилинии рейсов появятся после расчёта.
        </p>
      </div>
      <v-chip class="soft-chip" size="small" prepend-icon="mdi-map-outline">Mapbox · Day 5</v-chip>
    </header>

    <StatePanel
      class="map-state"
      :status="erp.panelStatus"
      :error-text="erp.errorMessage"
      loading-text="Загружаем точки складов и клиентов…"
      empty-title="Точек на карте пока нет"
      empty-icon="mdi-map-marker-off-outline"
      @retry="reload"
    >
      <div class="map-canvas neu-inset">
        <div class="canvas-grid" aria-hidden="true" />
        <div class="canvas-content">
          <v-icon icon="mdi-map-search-outline" size="34" color="primary" />
          <p class="canvas-title">Интерактивная карта подключается на Day 5</p>
          <p class="canvas-text">
            Маркеры складов и клиентов, слои маршрутов и попапы по клику. Пока — контрольный список
            точек с координатами.
          </p>
        </div>
      </div>

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
            <v-icon icon="mdi-storefront-outline" size="18" color="primary" /> Клиенты
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
                <span class="point-coords mono">
                  {{ client.lat.toFixed(4) }}, {{ client.lon.toFixed(4) }}
                </span>
              </span>
            </li>
          </ul>
        </div>
      </div>
    </StatePanel>
  </section>
</template>

<script setup lang="ts">
import StatePanel from '@/shared/components/StatePanel.vue'
import { useErpStore } from './useErpStore'

const erp = useErpStore()

function reload(): void {
  void erp.loadState({ force: true })
}
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

.map-state {
  flex: 1 1 auto;
  min-height: 0;
  overflow-y: auto;
}

.map-canvas {
  position: relative;
  display: grid;
  place-items: center;
  min-height: 220px;
  padding: 20px;
  overflow: hidden;
}

.canvas-grid {
  position: absolute;
  inset: 0;
  background-image:
    linear-gradient(rgba(91, 81, 117, 0.12) 1px, transparent 1px),
    linear-gradient(90deg, rgba(91, 81, 117, 0.12) 1px, transparent 1px);
  background-size: 40px 40px;
  pointer-events: none;
}

.canvas-content {
  position: relative;
  display: grid;
  justify-items: center;
  gap: 6px;
  text-align: center;
}

.canvas-title {
  margin: 0;
  font-weight: 600;
}

.canvas-text {
  margin: 0;
  max-width: 420px;
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

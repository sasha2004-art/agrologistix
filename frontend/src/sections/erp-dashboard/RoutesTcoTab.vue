<template>
  <div class="tab-body">
    <header class="tab-header">
      <div>
        <h2 class="tab-title">Маршруты и TCO</h2>
        <p class="tab-subtitle">
          План поставок, метрики TCO и сравнение «Было / Стало» появятся после подключения солвера.
        </p>
      </div>
    </header>

    <div class="run-row">
      <v-btn color="primary" class="btn-gradient" prepend-icon="mdi-routes" disabled>
        Рассчитать поставки
      </v-btn>
      <v-chip class="soft-chip" size="small" prepend-icon="mdi-progress-wrench">
        Солвер подключается на Day 7
      </v-chip>
    </div>

    <StatePanel
      :status="erp.panelStatus"
      :error-text="erp.errorMessage"
      loading-text="Готовим исходные данные для расчёта…"
      @retry="reload"
    >
      <div class="neu-inset plan-empty">
        <v-icon icon="mdi-map-marker-path" size="32" color="primary" />
        <p class="plan-title">План ещё не рассчитан</p>
        <p class="plan-text">
          Нажмите «Рассчитать поставки», когда солвер будет подключён: рейсы, полилинии и метрики
          TCO появятся здесь и на карте.
        </p>
      </div>

      <section class="risks">
        <h3 class="risks-title">Предварительные риски по исходным данным</h3>
        <p v-if="erp.riskAlerts.length === 0" class="risks-empty">
          Ограничений не найдено: автопарк, остатки и дороги согласованы.
        </p>
        <ul v-else class="risks-list">
          <li v-for="alert in erp.riskAlerts" :key="alert.id" class="risks-item">
            <v-icon
              :icon="alert.severity === 'error' ? 'mdi-alert-octagon-outline' : 'mdi-alert-outline'"
              :color="alert.severity === 'error' ? 'error' : 'warning'"
              size="18"
            />
            <span>{{ alert.message }}</span>
          </li>
        </ul>
      </section>
    </StatePanel>
  </div>
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
.tab-body {
  display: grid;
  gap: 16px;
}

.tab-header {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 12px;
}

.tab-title {
  margin: 0;
  font-size: 18px;
}

.tab-subtitle {
  margin: 4px 0 0;
  font-size: 13px;
  color: #5b5175;
}

.run-row {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 12px;
}

.plan-empty {
  display: grid;
  justify-items: center;
  gap: 6px;
  padding: 24px 18px;
  text-align: center;
}

.plan-title {
  margin: 0;
  font-weight: 600;
}

.plan-text {
  margin: 0;
  max-width: 420px;
  font-size: 13px;
  color: #5b5175;
}

.risks {
  margin-top: 18px;
}

.risks-title {
  margin: 0 0 8px;
  font-size: 14px;
}

.risks-empty {
  margin: 0;
  font-size: 13px;
  color: #5b5175;
}

.risks-list {
  display: grid;
  gap: 8px;
  margin: 0;
  padding: 0;
  list-style: none;
}

.risks-item {
  display: flex;
  align-items: flex-start;
  gap: 8px;
  font-size: 13px;
}
</style>

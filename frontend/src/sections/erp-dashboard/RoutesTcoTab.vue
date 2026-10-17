<template>
  <div class="tab-body">
    <header class="tab-header">
      <div>
        <h2 class="tab-title">Маршруты и TCO</h2>
        <p class="tab-subtitle">
          Расчёт на сервере: рейсы по машинам, полилинии на карте, метрики TCO и предупреждения.
        </p>
      </div>
      <v-chip v-if="solver.hasPlan" class="soft-chip" size="small" prepend-icon="mdi-clock-outline">
        {{ calculatedAtText }}
      </v-chip>
    </header>

    <div class="run-row">
      <v-btn
        color="primary"
        class="btn-gradient"
        prepend-icon="mdi-routes"
        :loading="solver.isLoading"
        :disabled="solver.isLoading || !erp.isReady"
        @click="runPlan"
      >
        {{ solver.hasPlan ? 'Пересчитать план' : 'Рассчитать поставки' }}
      </v-btn>
      <v-chip class="soft-chip" size="small" prepend-icon="mdi-server-outline">
        POST /solver/optimize
      </v-chip>
      <v-btn
        v-if="solver.hasPlan"
        variant="text"
        size="small"
        prepend-icon="mdi-close-circle-outline"
        @click="solver.clear()"
      >
        Сбросить план
      </v-btn>
    </div>

    <StatePanel
      :status="erp.panelStatus"
      :error-text="erp.errorMessage"
      loading-text="Готовим исходные данные для расчёта…"
      @retry="reload"
    >
      <div class="run-stack">
        <v-alert v-if="solver.status === 'error'" type="error" variant="tonal" class="run-error">
          <p class="run-error-text">{{ solver.errorMessage }}</p>
          <v-btn
            size="small"
            variant="text"
            prepend-icon="mdi-refresh"
            :loading="solver.isLoading"
            @click="runPlan"
          >
            Повторить расчёт
          </v-btn>
        </v-alert>

        <template v-if="solver.hasPlan">
          <TcoMetricsPanel />
          <SolverWarningsPanel />
          <RoutePlanTable />
        </template>
        <div v-else class="neu-inset plan-empty">
          <v-icon icon="mdi-map-marker-path" size="32" color="primary" />
          <p class="plan-title">
            {{ solver.isLoading ? 'Считаем план…' : 'План ещё не рассчитан' }}
          </p>
          <p class="plan-text">
            Нажмите «Рассчитать поставки»: сервер распределит заявки по машинам, посчитает свежесть,
            TCO и нарисует рейсы на карте.
          </p>
          <v-progress-linear
            v-if="solver.isLoading"
            class="plan-progress"
            indeterminate
            color="primary"
          />
        </div>

        <section class="risks">
          <h3 class="risks-title">Предварительные риски по исходным данным</h3>
          <p v-if="erp.riskAlerts.length === 0" class="risks-empty">
            Ограничений не найдено: автопарк, остатки и дороги согласованы.
          </p>
          <ul v-else class="risks-list">
            <li v-for="alert in erp.riskAlerts" :key="alert.id" class="risks-item">
              <v-icon
                :icon="
                  alert.severity === 'error' ? 'mdi-alert-octagon-outline' : 'mdi-alert-outline'
                "
                :color="alert.severity === 'error' ? 'error' : 'warning'"
                size="18"
              />
              <span>{{ alert.message }}</span>
            </li>
          </ul>
        </section>
      </div>
    </StatePanel>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import StatePanel from '@/shared/components/StatePanel.vue'
import RoutePlanTable from './RoutePlanTable.vue'
import SolverWarningsPanel from './SolverWarningsPanel.vue'
import TcoMetricsPanel from './TcoMetricsPanel.vue'
import { useErpStore } from './useErpStore'
import { useSolverStore } from './useSolverStore'
import { formatDateTime } from '@/shared/utils/format'

const erp = useErpStore()
const solver = useSolverStore()

const calculatedAtText = computed(() =>
  solver.calculatedAt ? `Рассчитано ${formatDateTime(solver.calculatedAt)}` : 'План получен',
)

function runPlan(): void {
  void solver.optimizeBaseline()
}

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

/* Внутри StatePanel слот не имеет собственных отступов — задаём их сами. */
.run-stack {
  display: grid;
  gap: 16px;
}

.run-error {
  display: grid;
  justify-items: start;
  gap: 6px;
}

.run-error-text {
  margin: 0;
  font-size: 13px;
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

.plan-progress {
  width: min(320px, 100%);
  margin-top: 8px;
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

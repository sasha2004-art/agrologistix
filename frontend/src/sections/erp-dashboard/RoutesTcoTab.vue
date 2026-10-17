<template>
  <div class="tab-body">
    <header class="tab-header">
      <div>
        <h2 class="tab-title">Маршруты и TCO</h2>
        <p class="tab-subtitle">
          Расчёт на сервере: рейсы по машинам, полилинии на карте, метрики TCO и предупреждения.
        </p>
      </div>
      <div class="header-chips">
        <v-chip
          v-if="solver.hasBaseline"
          class="soft-chip"
          size="small"
          prepend-icon="mdi-clock-outline"
        >
          {{ calculatedAtText }}
        </v-chip>
        <v-chip
          v-if="solver.hasScenario"
          class="soft-chip"
          size="small"
          variant="text"
          :color="solver.tcoDeltaWorse ? 'error' : 'success'"
          prepend-icon="mdi-compare-horizontal"
        >
          {{ solver.tcoDeltaLabel }}
        </v-chip>
      </div>
    </header>

    <div class="run-row">
      <v-btn
        color="primary"
        class="btn-gradient"
        prepend-icon="mdi-routes"
        :loading="solver.isLoading && solver.isRunning === 'baseline'"
        :disabled="solver.isLoading || !erp.isReady"
        @click="runPlan"
      >
        {{ solver.hasBaseline ? 'Пересчитать базу' : 'Рассчитать поставки' }}
      </v-btn>
      <v-btn
        v-if="solver.hasBaseline"
        variant="tonal"
        color="primary"
        prepend-icon="mdi-source-branch"
        :loading="solver.isLoading && solver.isRunning === 'what_if'"
        :disabled="solver.isLoading"
        @click="solver.runScenario()"
      >
        Сценарий «что, если»
      </v-btn>
      <v-btn
        v-if="solver.hasScenario"
        variant="text"
        prepend-icon="mdi-compare-horizontal"
        @click="comparisonOpen = true"
      >
        Было / Стало
      </v-btn>
      <v-chip class="soft-chip" size="small" prepend-icon="mdi-server-outline">
        POST /solver/optimize
      </v-chip>
      <v-btn
        v-if="solver.hasBaseline"
        variant="text"
        size="small"
        prepend-icon="mdi-close-circle-outline"
        @click="solver.clear()"
      >
        Сбросить план
      </v-btn>
    </div>

    <div v-if="solver.hasBaseline" class="export-row">
      <v-btn
        variant="tonal"
        color="primary"
        prepend-icon="mdi-file-excel-outline"
        :loading="exporting"
        :disabled="exporting || !activeRunId"
        @click="exportXlsx"
      >
        Скачать XLSX
      </v-btn>
      <v-btn variant="tonal" color="primary" prepend-icon="mdi-printer" @click="printSheet">
        Печать / PDF
      </v-btn>
      <v-chip
        class="soft-chip"
        size="small"
        prepend-icon="mdi-truck-outline"
        :title="routesInSheetText"
      >
        В лист: {{ solver.routes.length }} рейс(а) · {{ solver.plannedStops.length }} стоп(ов)
      </v-chip>
    </div>

    <v-alert
      v-if="solver.hasBaseline && solver.scenarioStale"
      type="info"
      variant="tonal"
      density="comfortable"
      class="stale-note"
    >
      ERP изменился —
      {{ solver.isLoading ? 'сценарий пересчитывается…' : 'сценарий пересчитается автоматически.' }}
    </v-alert>

    <v-btn-toggle
      v-if="solver.hasScenario"
      :model-value="solver.view"
      mandatory
      density="comfortable"
      class="view-toggle"
      @update:model-value="onViewChange"
    >
      <v-btn value="baseline" prepend-icon="mdi-map-marker-path">Базовый план</v-btn>
      <v-btn value="scenario" prepend-icon="mdi-source-branch">Сценарий</v-btn>
    </v-btn-toggle>

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

        <template v-if="solver.hasBaseline">
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

    <ComparisonDialog v-model="comparisonOpen" />
  </div>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue'
import { describeApiError, downloadRouteSheet } from '@/shared/api/httpClient'
import StatePanel from '@/shared/components/StatePanel.vue'
import ComparisonDialog from './ComparisonDialog.vue'
import RoutePlanTable from './RoutePlanTable.vue'
import SolverWarningsPanel from './SolverWarningsPanel.vue'
import TcoMetricsPanel from './TcoMetricsPanel.vue'
import { useErpStore } from './useErpStore'
import { useSolverStore } from './useSolverStore'
import { useAuthStore } from '@/sections/pin-auth/useAuthStore'
import { useNotificationStore } from '@/shared/stores/useNotificationStore'
import { formatDateTime } from '@/shared/utils/format'
import { triggerDownload } from '@/shared/utils/download'

const erp = useErpStore()
const solver = useSolverStore()
const auth = useAuthStore()
const notifications = useNotificationStore()
const comparisonOpen = ref(false)
const exporting = ref(false)

/** Прогон, который уйдёт в файл и на печать: тот, что сейчас на экране. */
const activeRunId = computed(() => solver.activePlan?.run_id ?? null)

/** Подсказка к чипу: какие именно рейсы попадут в маршрутный лист. */
const routesInSheetText = computed(() =>
  solver.routes.map((route) => `${route.truck_name} (${route.stops.length})`).join(', '),
)

/** Печать текущего вида: браузер показывает только печатный лист (print.scss). */
function printSheet(): void {
  window.print()
}

async function exportXlsx(): Promise<void> {
  const runId = activeRunId.value
  const pin = auth.accessPin
  if (!runId || !pin || exporting.value) return
  exporting.value = true
  try {
    const { blob, filename } = await downloadRouteSheet(runId, pin)
    triggerDownload(blob, filename)
    notifications.push('success', `Маршрутный лист сохранён: ${filename}`)
  } catch (error) {
    notifications.push('error', describeApiError(error))
  } finally {
    exporting.value = false
  }
}

const calculatedAtText = computed(() =>
  solver.calculatedAt ? `Рассчитано ${formatDateTime(solver.calculatedAt)}` : 'План получен',
)

function runPlan(): void {
  void solver.optimizeBaseline()
}

function onViewChange(next: unknown): void {
  if (next === 'baseline' || next === 'scenario') solver.setView(next)
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

.header-chips {
  display: flex;
  flex-direction: column;
  align-items: flex-end;
  gap: 6px;
}

.stale-note {
  font-size: 13px;
}

.view-toggle {
  align-self: flex-start;
}

/* Внутри StatePanel слот не имеет собственных отступов — задаём их сами. */
.run-stack {
  display: grid;
  gap: 16px;
}

.export-row {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 12px;
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

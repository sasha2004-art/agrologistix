<template>
  <div class="tab-body">
    <header class="tab-header">
      <div>
        <h2 class="tab-title">Расчёт маршрутов</h2>
        <p class="tab-subtitle">Машины, маршруты, затраты и сохранность урожая.</p>
      </div>
      <div class="header-chips">
        <v-chip
          v-if="solver.hasPlan"
          class="soft-chip"
          size="small"
          prepend-icon="mdi-clock-outline"
        >
          {{ calculatedAtText }}
        </v-chip>
      </div>
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
        {{ solver.hasPlan ? 'Пересчитать' : 'Рассчитать поставки' }}
      </v-btn>
      <v-btn
        v-if="solver.hasPlan"
        variant="text"
        size="small"
        prepend-icon="mdi-close-circle-outline"
        @click="solver.clear()"
      >
        Очистить
      </v-btn>
    </div>

    <div v-if="solver.hasPlan" class="export-row">
      <v-btn
        variant="tonal"
        color="primary"
        prepend-icon="mdi-file-excel-outline"
        :loading="exporting"
        :disabled="exporting || !activeRunId"
        @click="exportXlsx"
      >
        Скачать таблицу (Excel)
      </v-btn>
      <v-btn variant="tonal" color="primary" prepend-icon="mdi-printer" @click="printSheet">
        Печать / PDF
      </v-btn>
      <v-btn
        variant="tonal"
        color="primary"
        prepend-icon="mdi-check-all"
        :loading="erp.isPending(ORDERS_DELIVER_KEY)"
        :disabled="erp.isPending(ORDERS_DELIVER_KEY) || deliverableOrderIds.length === 0"
        :title="deliverHint"
        @click="markPlanDelivered"
      >
        Отметить доставленными
      </v-btn>
      <v-chip
        class="soft-chip"
        size="small"
        prepend-icon="mdi-truck-outline"
        :title="routesInSheetText"
      >
        В лист: {{ solver.routes.length }} машин, {{ solver.plannedStops.length }} остановок
      </v-chip>
    </div>

    <v-alert
      v-if="solver.hasPlan && solver.planStale"
      type="info"
      variant="tonal"
      density="comfortable"
      class="stale-note"
    >
      Данные изменились — пересчитайте маршруты, чтобы увидеть актуальные цифры.
    </v-alert>

    <StatePanel
      :status="erp.panelStatus"
      :error-text="erp.errorMessage"
      loading-text="Готовим данные для расчёта…"
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
          <SolverWarningsPanel />
          <RoutePlanTable />
        </template>
        <div v-else class="neu-inset plan-empty">
          <v-icon icon="mdi-map-marker-path" size="32" color="primary" />
          <p class="plan-title">
            {{ solver.isLoading ? 'Считаем…' : 'Маршруты ещё не рассчитаны' }}
          </p>
          <p class="plan-text">
            Нажмите «Рассчитать поставки»: сервис распределит заказы по машинам, посчитает
            сохранность урожая и нарисует маршруты на карте.
          </p>
          <v-progress-linear
            v-if="solver.isLoading"
            class="plan-progress"
            indeterminate
            color="primary"
          />
        </div>

        <section class="risks">
          <h3 class="risks-title">На что обратить внимание</h3>
          <p v-if="erp.riskAlerts.length === 0" class="risks-empty">
            Замечаний нет: машины, остатки и дороги согласованы.
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
import { computed, ref } from 'vue'
import { describeApiError, downloadRouteSheet } from '@/shared/api/httpClient'
import StatePanel from '@/shared/components/StatePanel.vue'
import RoutePlanTable from './RoutePlanTable.vue'
import SolverWarningsPanel from './SolverWarningsPanel.vue'
import { ORDERS_DELIVER_KEY, useErpStore } from './useErpStore'
import { useSolverStore } from './useSolverStore'
import { useAuthStore } from '@/sections/pin-auth/useAuthStore'
import { useNotificationStore } from '@/shared/stores/useNotificationStore'
import { formatDateTime } from '@/shared/utils/format'
import { triggerDownload } from '@/shared/utils/download'

const erp = useErpStore()
const solver = useSolverStore()
const auth = useAuthStore()
const notifications = useNotificationStore()
const exporting = ref(false)

/** Прогон, который попадает в XLSX и на печать. */
const activeRunId = computed(() => solver.plan?.run_id ?? null)

/** Подсказка к чипу: какие именно машины попадут в маршрутный лист. */
const routesInSheetText = computed(() =>
  solver.routes.map((route) => `${route.truck_name} (${route.stops.length})`).join(', '),
)

/** Печать текущего плана: браузер показывает только печатный лист (print.scss). */
function printSheet(): void {
  window.print()
}

/** Заказы, которые есть в плане и ещё не отмечены доставленными. */
const deliverableOrderIds = computed(() => {
  const plannedIds = new Set(
    solver.plannedStops
      .map((item) => item.stop.order_id)
      .filter((id): id is number => id !== null && id !== undefined),
  )
  return erp.pendingOrders.map((row) => row.order.id).filter((id) => plannedIds.has(id))
})

const deliverHint = computed(() =>
  deliverableOrderIds.value.length > 0
    ? `Отметить доставленными заказов: ${deliverableOrderIds.value.length}`
    : 'Все заказы плана уже отмечены доставленными',
)

/** Массовая доставка: по одному PATCH на заказ, сток списывает backend по плану. */
function markPlanDelivered(): void {
  void erp.deliverOrders(deliverableOrderIds.value)
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
  void solver.optimizePlan()
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

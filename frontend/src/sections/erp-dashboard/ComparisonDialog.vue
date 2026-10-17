<template>
  <v-dialog v-model="open" max-width="720" scrollable>
    <v-card class="comparison-card">
      <v-card-title class="comparison-title">
        <span>Было / Стало</span>
        <v-chip class="soft-chip" size="small" prepend-icon="mdi-source-branch">
          прогон №{{ scenarioRunId ?? '—' }} ← база №{{ solver.baselineRunId ?? '—' }}
        </v-chip>
      </v-card-title>

      <v-card-subtitle class="comparison-subtitle">
        Сценарий пересчитан по актуальным заявкам, машинам и ценам. Базовый план не изменялся.
      </v-card-subtitle>

      <v-card-text class="comparison-body">
        <v-table density="comfortable" class="erp-table">
          <thead>
            <tr>
              <th scope="col">Метрика</th>
              <th scope="col" class="text-right">Было</th>
              <th scope="col" class="text-right">Стало</th>
              <th scope="col" class="text-right">Изменение</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="row in rows" :key="row.key">
              <td>{{ row.label }}</td>
              <td class="text-right mono">{{ row.before }}</td>
              <td class="text-right mono">{{ row.after }}</td>
              <td class="text-right">
                <MetricDelta
                  :delta="row.delta"
                  :unit="row.unit"
                  :higher-is-better="row.higherIsBetter"
                />
              </td>
            </tr>
          </tbody>
        </v-table>
      </v-card-text>

      <v-card-actions class="comparison-actions">
        <v-btn variant="text" prepend-icon="mdi-swap-horizontal" @click="switchToScenario">
          Показать сценарий на карте
        </v-btn>
        <v-spacer />
        <v-btn variant="text" @click="open = false">Закрыть</v-btn>
      </v-card-actions>
    </v-card>
  </v-dialog>
</template>

<script setup lang="ts">
import { computed, watch } from 'vue'
import MetricDelta from './MetricDelta.vue'
import { useSolverStore } from './useSolverStore'
import type { MetricDelta as MetricDeltaValue } from '@/shared/types/domain'
import { formatKg, formatPercent, formatRub } from '@/shared/utils/format'

const open = defineModel<boolean>({ default: false })
const solver = useSolverStore()

const scenarioRunId = computed(() => solver.scenario?.run_id ?? null)

interface Row {
  key: string
  label: string
  before: string
  after: string
  delta: MetricDeltaValue
  unit: 'rub' | 'kg' | 'percent'
  higherIsBetter: boolean
}

const rows = computed<Row[]>(() => {
  const c = solver.comparison
  if (!c) return []
  return [
    {
      key: 'total_tco_rub',
      label: 'Совокупные затраты (TCO)',
      before: formatRub(c.total_tco_rub.before),
      after: formatRub(c.total_tco_rub.after),
      delta: c.total_tco_rub,
      unit: 'rub',
      higherIsBetter: false,
    },
    {
      key: 'total_trip_cost_rub',
      label: 'Стоимость рейсов',
      before: formatRub(c.total_trip_cost_rub.before),
      after: formatRub(c.total_trip_cost_rub.after),
      delta: c.total_trip_cost_rub,
      unit: 'rub',
      higherIsBetter: false,
    },
    {
      key: 'total_spoilage_loss_rub',
      label: 'Потери от порчи',
      before: formatRub(c.total_spoilage_loss_rub.before),
      after: formatRub(c.total_spoilage_loss_rub.after),
      delta: c.total_spoilage_loss_rub,
      unit: 'rub',
      higherIsBetter: false,
    },
    {
      key: 'total_unmet_penalty_rub',
      label: 'Штраф за недовоз',
      before: formatRub(c.total_unmet_penalty_rub.before),
      after: formatRub(c.total_unmet_penalty_rub.after),
      delta: c.total_unmet_penalty_rub,
      unit: 'rub',
      higherIsBetter: false,
    },
    {
      key: 'expected_net_profit_rub',
      label: 'Ожидаемая прибыль',
      before: formatRub(c.expected_net_profit_rub.before),
      after: formatRub(c.expected_net_profit_rub.after),
      delta: c.expected_net_profit_rub,
      unit: 'rub',
      higherIsBetter: true,
    },
    {
      key: 'avg_freshness_pct',
      label: 'Средняя свежесть',
      before: formatPercent(c.avg_freshness_pct.before),
      after: formatPercent(c.avg_freshness_pct.after),
      delta: c.avg_freshness_pct,
      unit: 'percent',
      higherIsBetter: true,
    },
    {
      key: 'shipped_kg',
      label: 'Отгружено',
      before: formatKg(c.shipped_kg.before),
      after: formatKg(c.shipped_kg.after),
      delta: c.shipped_kg,
      unit: 'kg',
      higherIsBetter: true,
    },
    {
      key: 'unmet_kg',
      label: 'Недовоз',
      before: formatKg(c.unmet_kg.before),
      after: formatKg(c.unmet_kg.after),
      delta: c.unmet_kg,
      unit: 'kg',
      higherIsBetter: false,
    },
  ]
})

function switchToScenario(): void {
  solver.setView('scenario')
  open.value = false
}

// Диалог всегда показывает свежие данные: окно закрывается, если сравнение пропало.
watch(
  () => solver.comparison,
  (next) => {
    if (!next) open.value = false
  },
)
</script>

<style scoped lang="scss">
.comparison-card {
  background: var(--neu-bg);
}

.comparison-title {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  font-size: 16px;
}

.comparison-subtitle {
  font-size: 12px;
  color: #5b5175;
}

.comparison-body {
  padding-top: 8px;
}

.comparison-actions {
  padding: 8px 16px 12px;
}
</style>

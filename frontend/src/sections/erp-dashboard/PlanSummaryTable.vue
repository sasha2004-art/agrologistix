<template>
  <section class="summary" aria-label="Итоги расчёта">
    <h3 class="summary-title">Итоги расчёта</h3>

    <v-table density="comfortable" class="excel-table">
      <thead>
        <tr>
          <th scope="col">Показатель</th>
          <th scope="col" class="text-right">Значение</th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="row in rows" :key="row.label" :class="row.modifier ? `row-${row.modifier}` : ''">
          <td>
            {{ row.label }}
            <span class="cell-note">{{ row.hint }}</span>
          </td>
          <td class="text-right mono">{{ row.value }}</td>
        </tr>
      </tbody>
    </v-table>
  </section>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { useSolverStore } from './useSolverStore'
import type { Metrics } from '@/shared/types/domain'
import { formatKg, formatPercent, formatRub } from '@/shared/utils/format'
import { freshnessLabel, freshnessLevel } from '@/shared/utils/freshness'

const EMPTY_METRICS: Metrics = {
  total_tco_rub: 0,
  total_trip_cost_rub: 0,
  total_spoilage_loss_rub: 0,
  expected_net_profit_rub: 0,
  avg_freshness_pct: 0,
  spoilage_pct: 0,
  unmet_pct: 0,
  shipped_kg: 0,
  unmet_kg: 0,
  total_trips: 0,
  avg_load_factor_pct: 0,
  split_clients: 0,
}

interface SummaryRow {
  label: string
  value: string
  hint: string
  modifier?: string
}

const solver = useSolverStore()
const metrics = computed<Metrics>(() => solver.metrics ?? EMPTY_METRICS)

/** Итоговые деньги, траты и прибыль одной excel-таблицей в начале вкладки. */
const rows = computed<SummaryRow[]>(() => {
  const m = metrics.value
  const freshness = freshnessLevel(m.avg_freshness_pct / 100)
  const result: SummaryRow[] = [
    {
      label: 'Итоговая стоимость',
      value: formatRub(m.total_tco_rub),
      hint: 'доставка и потери урожая',
    },
    {
      label: 'Затраты на доставку',
      value: formatRub(m.total_trip_cost_rub),
      hint: `${m.total_trips} рейсов, загрузка ${formatPercent(m.avg_load_factor_pct)}`,
    },
    {
      label: 'Потери урожая',
      value: formatRub(m.total_spoilage_loss_rub),
      hint: `${formatPercent(m.spoilage_pct)} груза испортилось в пути`,
    },
    {
      label: 'Прибыль',
      value: formatRub(m.expected_net_profit_rub),
      hint: `${formatKg(m.shipped_kg)} привезли`,
    },
    {
      label: 'Сохранность урожая',
      value: formatPercent(m.avg_freshness_pct),
      hint: freshnessLabel(m.avg_freshness_pct / 100),
      modifier: freshness,
    },
  ]

  if (m.unmet_pct > 0) {
    result.push({
      label: 'Не привезли',
      value: formatKg(m.unmet_kg),
      hint: `${formatPercent(m.unmet_pct)} от заказанного объёма`,
      modifier: 'error',
    })
  }

  return result
})
</script>

<style scoped lang="scss">
.summary {
  display: grid;
  gap: 8px;
}

.summary-title {
  margin: 0;
  font-size: 15px;
}

.cell-note {
  display: block;
  font-size: 11px;
  color: #5b5175;
  white-space: normal;
}

/* Подсветка строк по свежести: значение в ячейке, цвет лишь дополняет его. */
.row-warning {
  background: rgba(245, 158, 11, 0.12);
}

.row-error {
  background: rgba(190, 18, 60, 0.12);
}
</style>

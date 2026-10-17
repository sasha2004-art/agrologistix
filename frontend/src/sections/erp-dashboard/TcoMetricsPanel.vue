<template>
  <section class="tco" aria-label="Затраты и прибыль по плану">
    <div class="tco-head">
      <h3 class="tco-title">Затраты и прибыль</h3>
      <v-chip class="soft-chip" size="small" prepend-icon="mdi-calculator-variant-outline">
        {{ solver.routes.length }} машин · {{ solver.plannedStops.length }} остановок
      </v-chip>
    </div>

    <div class="tco-grid">
      <div
        v-for="card in cards"
        :key="card.label"
        class="tco-card neu-inset"
        :class="card.modifier ? `tco-card--${card.modifier}` : ''"
      >
        <span class="tco-label">{{ card.label }}</span>
        <span class="tco-value mono">{{ card.value }}</span>
        <span class="tco-hint">{{ card.hint }}</span>
      </div>
    </div>
  </section>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { useSolverStore } from './useSolverStore'
import type { Metrics } from '@/shared/types/domain'
import { formatKg, formatNumber, formatPercent, formatRub } from '@/shared/utils/format'
import { freshnessLevel, freshnessLabel } from '@/shared/utils/freshness'

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

interface Card {
  label: string
  value: string
  hint: string
  modifier?: string
}

const solver = useSolverStore()

const metrics = computed<Metrics>(() => solver.metrics ?? EMPTY_METRICS)

const freshnessFraction = computed(() => metrics.value.avg_freshness_pct / 100)
const freshness = computed(() => freshnessLevel(freshnessFraction.value))

const cards = computed<Card[]>(() => {
  const m = metrics.value
  return [
    {
      label: 'Общие затраты',
      value: formatRub(m.total_tco_rub),
      hint: 'доставка и потери урожая',
    },
    {
      label: 'Затраты на доставку',
      value: formatRub(m.total_trip_cost_rub),
      hint: 'дорога и выезд',
    },
    {
      label: 'Потери урожая',
      value: formatRub(m.total_spoilage_loss_rub),
      hint: `${formatPercent(m.spoilage_pct)} груза испортилось в пути`,
    },
    ...(m.unmet_pct > 0
      ? [
          {
            label: 'Не привезли',
            value: formatPercent(m.unmet_pct),
            hint: `${formatKg(m.unmet_kg)} от заказанного объёма`,
            modifier: 'alert',
          },
        ]
      : []),
    {
      label: 'Прибыль',
      value: formatRub(m.expected_net_profit_rub),
      hint: `${formatKg(m.shipped_kg)} привезли`,
    },
    {
      label: 'Сохранность урожая',
      value: formatPercent(m.avg_freshness_pct),
      hint: freshnessLabel(freshnessFraction.value),
      modifier: freshness.value,
    },
    {
      // Консолидация: сколько рейсов вышло и насколько полно загружены машины.
      label: 'Загрузка машин',
      value: formatPercent(m.avg_load_factor_pct),
      hint: `${formatNumber(m.total_trips)} рейсов · покупателей в двух машинах: ${formatNumber(m.split_clients)}`,
    },
  ]
})
</script>

<style scoped lang="scss">
.tco {
  display: grid;
  gap: 10px;
}

.tco-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
  flex-wrap: wrap;
}

.tco-title {
  margin: 0;
  font-size: 15px;
}

.tco-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(168px, 1fr));
  gap: 10px;
}

.tco-card {
  display: grid;
  gap: 2px;
  padding: 12px;
}

.tco-label {
  font-size: 12px;
  color: #5b5175;
}

.tco-value {
  font-size: 17px;
  font-weight: 600;
}

.tco-hint {
  font-size: 11px;
  color: #5b5175;
}

.tco-card--alert,
.tco-card--error {
  border-color: rgba(190, 18, 60, 0.55);
}

.tco-card--warning {
  border-color: rgba(180, 83, 9, 0.55);
}
</style>

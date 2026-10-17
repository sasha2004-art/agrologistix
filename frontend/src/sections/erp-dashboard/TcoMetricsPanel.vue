<template>
  <section class="tco" aria-label="Метрики TCO рассчитанного плана">
    <div class="tco-head">
      <h3 class="tco-title">TCO рассчитанного плана</h3>
      <v-chip class="soft-chip" size="small" prepend-icon="mdi-calculator-variant-outline">
        {{ solver.routes.length }} рейс(а) · {{ solver.plannedStops.length }} стоп(ов)
      </v-chip>
    </div>

    <div class="tco-grid">
      <div class="tco-card neu-inset">
        <span class="tco-label">Совокупные затраты</span>
        <span class="tco-value mono">{{ formatRub(metrics.total_tco_rub) }}</span>
        <span class="tco-hint">рейсы + порча + штрафы</span>
      </div>

      <div class="tco-card neu-inset">
        <span class="tco-label">Стоимость рейсов</span>
        <span class="tco-value mono">{{ formatRub(metrics.total_trip_cost_rub) }}</span>
        <span class="tco-hint">топливо, время, фикс</span>
      </div>

      <div class="tco-card neu-inset">
        <span class="tco-label">Потери от порчи</span>
        <span class="tco-value mono">{{ formatRub(metrics.total_spoilage_loss_rub) }}</span>
        <span class="tco-hint">по свежести на выгрузке</span>
      </div>

      <div
        class="tco-card neu-inset"
        :class="{ 'tco-card--alert': metrics.total_unmet_penalty_rub > 0 }"
      >
        <span class="tco-label">Штраф за недовоз</span>
        <span class="tco-value mono">{{ formatRub(metrics.total_unmet_penalty_rub) }}</span>
        <span class="tco-hint">{{ formatKg(metrics.unmet_kg) }} не закрыто</span>
      </div>

      <div class="tco-card neu-inset">
        <span class="tco-label">Ожидаемая прибыль</span>
        <span class="tco-value mono">{{ formatRub(metrics.expected_net_profit_rub) }}</span>
        <span class="tco-hint">{{ formatKg(metrics.shipped_kg) }} отгружено</span>
      </div>

      <div class="tco-card neu-inset" :class="`tco-card--${freshness}`">
        <span class="tco-label">Средняя свежесть</span>
        <span class="tco-value mono">{{ formatPercent(metrics.avg_freshness_pct) }}</span>
        <span class="tco-hint">{{ freshnessText }}</span>
      </div>
    </div>
  </section>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { useSolverStore } from './useSolverStore'
import { formatKg, formatPercent, formatRub } from '@/shared/utils/format'
import { freshnessLevel, freshnessLabel } from '@/shared/utils/freshness'

const EMPTY_METRICS = {
  total_tco_rub: 0,
  total_trip_cost_rub: 0,
  total_spoilage_loss_rub: 0,
  total_unmet_penalty_rub: 0,
  expected_net_profit_rub: 0,
  avg_freshness_pct: 0,
  shipped_kg: 0,
  unmet_kg: 0,
}

const solver = useSolverStore()

/** Панель показывается только при наличии плана, но тип метрик всё равно сузим. */
const metrics = computed(() => solver.metrics ?? EMPTY_METRICS)
const freshness = computed(() => freshnessLevel((solver.metrics?.avg_freshness_pct ?? 100) / 100))
const freshnessText = computed(() =>
  freshnessLabel((solver.metrics?.avg_freshness_pct ?? 100) / 100),
)
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
}

.tco-title {
  margin: 0;
  font-size: 15px;
}

.tco-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(158px, 1fr));
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

<template>
  <span v-if="!delta" class="delta delta--none">нет сравнения</span>
  <span v-else class="delta" :class="`delta--${tone}`" :title="title">
    {{ sign }}{{ absoluteText }}<span v-if="percentText"> ({{ percentText }})</span>
  </span>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import type { MetricDelta } from '@/shared/types/domain'
import { formatDecimal, formatKg, formatNumber, formatRub } from '@/shared/utils/format'

const props = withDefaults(
  defineProps<{
    delta?: MetricDelta | null
    /** Единица измерения: влияет только на формат абсолютного значения. */
    unit?: 'rub' | 'kg' | 'percent'
    /** true — рост метрики это улучшение (прибыль, свежесть), false — ухудшение (затраты, недовоз). */
    higherIsBetter?: boolean
  }>(),
  { delta: null, unit: 'rub', higherIsBetter: true },
)

const EPSILON = 1e-6

const absoluteText = computed(() => {
  const value = Math.abs(props.delta?.delta ?? 0)
  if (props.unit === 'kg') return formatKg(value)
  if (props.unit === 'percent') return `${formatDecimal(value)} п.п.`
  return formatRub(value)
})

const percentText = computed(() => {
  const pct = props.delta?.delta_pct
  if (pct === null || pct === undefined) return ''
  if (Math.abs(pct) < 0.05) return formatNumber(0) + ' %'
  return `${formatDecimal(Math.abs(pct))} %`
})

const sign = computed(() => {
  const value = props.delta?.delta ?? 0
  if (Math.abs(value) < EPSILON) return ''
  return value > 0 ? '+' : '−'
})

const tone = computed(() => {
  const value = props.delta?.delta ?? 0
  if (Math.abs(value) < EPSILON) return 'same'
  const improved = props.higherIsBetter ? value > 0 : value < 0
  return improved ? 'good' : 'bad'
})

const title = computed(() => {
  if (!props.delta) return 'Сценарий ещё не рассчитан'
  return `Было ${formatNumber(props.delta.before)} → стало ${formatNumber(props.delta.after)}`
})
</script>

<style scoped lang="scss">
.delta {
  font-size: 12px;
  font-variant-numeric: tabular-nums;
  white-space: nowrap;
}

.delta--good {
  color: #047857;
}

.delta--bad {
  color: #be123c;
}

.delta--same,
.delta--none {
  color: #5b5175;
}
</style>

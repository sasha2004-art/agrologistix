<template>
  <section class="warnings" aria-label="Замечания к расчёту">
    <div class="warnings-head">
      <h3 class="warnings-title">Замечания к расчёту</h3>
      <v-chip
        v-if="solver.warnings.length > 0"
        class="soft-chip"
        size="small"
        prepend-icon="mdi-alert-outline"
      >
        Замечаний: {{ solver.warnings.length }}
      </v-chip>
      <v-chip v-else class="soft-chip" size="small" prepend-icon="mdi-check-circle-outline">
        Замечаний нет
      </v-chip>
    </div>

    <ul v-if="solver.warnings.length > 0" class="warnings-list">
      <li
        v-for="warning in solver.warnings"
        :key="warning.code + (warning.order_id ?? '')"
        class="warning-item"
        :class="`warning-item--${warning.severity}`"
      >
        <!-- Иконка несёт короткий заголовок, а текст-деталь приходит от сервера. -->
        <v-icon
          :icon="warningMeta(warning.code).icon"
          :color="warningColor(warning.severity)"
          size="18"
          :title="warningMeta(warning.code).title"
          :aria-label="warningMeta(warning.code).title"
        />
        <span class="warning-text">{{ warning.message }}</span>
        <v-chip
          v-if="warningTarget(warning)"
          class="soft-chip warning-target"
          size="x-small"
          variant="text"
          :prepend-icon="warning.order_id ? 'mdi-clipboard-text-outline' : 'mdi-account-outline'"
        >
          {{ warningTarget(warning) }}
        </v-chip>
      </li>
    </ul>

    <v-table
      v-if="solver.riskyStops.length > 0"
      density="comfortable"
      class="excel-table risky-table"
    >
      <thead>
        <tr>
          <th scope="col">
            <span class="risky-head">
              <v-icon icon="mdi-thermometer-low" color="warning" size="16" aria-hidden="true" />
              Точки с низкой сохранностью ({{ solver.riskyStops.length }} из
              {{ solver.plannedStops.length }})
            </span>
          </th>
        </tr>
      </thead>
      <tbody>
        <tr
          v-for="item in solver.riskyStops"
          :key="item.stop.order_id ?? item.stop.client_id"
          :class="`row-${item.freshness}`"
        >
          <td>
            <span class="risky-row">
              <span class="risky-dot" :style="{ background: item.color }" aria-hidden="true" />
              <span class="risky-text">
                {{ clientName(item.stop.client_id) }} · заказ №{{ item.stop.order_id ?? '—' }} ·
                {{ truckName(item.truckId) }} · в пути {{ formatMinutes(item.stop.eta_minutes) }} ·
                сохранность {{ formatFreshness(item.stop.expected_freshness) }}
              </span>
              <v-chip
                class="soft-chip"
                size="x-small"
                :color="item.freshness === 'error' ? 'error' : 'warning'"
                variant="text"
              >
                {{ freshnessLabel(item.stop.expected_freshness) }}
              </v-chip>
            </span>
          </td>
        </tr>
      </tbody>
    </v-table>
  </section>
</template>

<script setup lang="ts">
import { useSolverStore } from './useSolverStore'
import { useErpStore } from './useErpStore'
import { formatFreshness, formatMinutes } from '@/shared/utils/format'
import { freshnessLabel } from '@/shared/utils/freshness'
import { warningColor, warningMeta, warningTarget } from '@/shared/utils/solverWarnings'

const solver = useSolverStore()
const erp = useErpStore()

function clientName(clientId: number): string {
  return erp.clientById.get(clientId)?.name ?? `Покупатель №${clientId}`
}

function truckName(truckId: number): string {
  return erp.truckById.get(truckId)?.name ?? `Машина №${truckId}`
}
</script>

<style scoped lang="scss">
.warnings {
  display: grid;
  gap: 10px;
}

.warnings-head {
  display: flex;
  align-items: center;
  gap: 10px;
  flex-wrap: wrap;
}

.warnings-title {
  margin: 0;
  font-size: 15px;
}

.warnings-list {
  display: grid;
  gap: 8px;
  margin: 0;
  padding: 0;
  list-style: none;
}

.warning-item {
  display: flex;
  align-items: flex-start;
  gap: 8px;
  padding-left: 8px;
  font-size: 13px;
  /* Полоска слева: уровень предупреждения виден без чтения текста. */
  border-left: 3px solid transparent;
}

.warning-item--error {
  border-left-color: #be123c;
}

.warning-item--warning {
  border-left-color: #f59e0b;
}

.warning-item--info {
  border-left-color: #0369a1;
}

.warning-text {
  flex: 1 1 auto;
}

.warning-target {
  flex: 0 0 auto;
}

/* Эксельные строки низкой сохранности: таблица из одной колонки.
   Текст в ней длинный, поэтому переносим его, в отличие от остальных таблиц. */
.risky-table {
  margin-top: 4px;
}

.risky-table :deep(td) {
  white-space: normal;
}

.risky-head {
  display: inline-flex;
  align-items: center;
  gap: 6px;
}

.risky-row {
  display: flex;
  align-items: center;
  gap: 8px;
}

.risky-text {
  flex: 1 1 auto;
}

/* Подсветка строк по свежести: значение — в ячейке, цвет — дополняет его. */
.row-warning {
  background: rgba(245, 158, 11, 0.12);
}

.row-error {
  background: rgba(190, 18, 60, 0.12);
}

.risky-dot {
  flex: 0 0 auto;
  width: 10px;
  height: 10px;
  border-radius: 50%;
}
</style>

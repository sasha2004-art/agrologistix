<template>
  <section class="plan" aria-label="Рейсы рассчитанного плана">
    <h3 class="plan-title">Маршруты</h3>

    <article v-for="route in solver.routes" :key="route.truck_id" class="route-card neu-inset">
      <header class="route-head">
        <span
          class="route-swatch"
          :style="{ background: colorOf(route.truck_id) }"
          aria-hidden="true"
        />
        <span class="route-name">{{ route.truck_name }}</span>
        <span class="route-meta mono">
          {{ formatKm(route.total_distance_km) }} · {{ formatMinutes(route.total_duration_min) }} ·
          {{ formatRub(route.total_cost_rub) }}
        </span>
        <v-chip class="soft-chip" size="x-small">{{ route.stops.length }} остановок</v-chip>
      </header>

      <v-table density="compact" class="excel-table">
        <thead>
          <tr>
            <th scope="col" class="text-right">#</th>
            <th scope="col">Покупатель</th>
            <th scope="col">Урожай</th>
            <th scope="col" class="text-right">Вес</th>
            <th scope="col" class="text-right">Расстояние</th>
            <th scope="col" class="text-right">В пути</th>
            <th scope="col" class="text-right">Сохранность</th>
            <th scope="col" class="text-right">Стоимость</th>
            <th scope="col">Статус</th>
          </tr>
        </thead>
        <tbody>
          <tr
            v-for="stop in route.stops"
            :key="`${route.truck_id}-${stop.order_id ?? stop.client_id}`"
            :class="`row-${freshnessLevel(stop.expected_freshness)}`"
          >
            <td class="text-right mono">{{ stop.sequence_order }}</td>
            <td>
              {{ clientName(stop.client_id) }}
              <!-- Грунтовка влияет на время в пути и свежесть: показываем прямо в плане. -->
              <span v-if="isDirt(stop.client_id)" class="dirt-note">
                <v-icon icon="mdi-road-variant" size="13" color="warning" aria-hidden="true" />
                грунтовка
              </span>
            </td>
            <td>{{ productName(stop.product_id) }}</td>
            <td class="text-right mono">{{ formatKg(stop.shipped_kg) }}</td>
            <td class="text-right mono">{{ formatKm(stop.distance_km) }}</td>
            <td class="text-right mono">{{ formatMinutes(stop.eta_minutes) }}</td>
            <td class="text-right mono">{{ formatFreshness(stop.expected_freshness) }}</td>
            <td class="text-right mono">{{ formatRub(stop.trip_leg_cost_rub) }}</td>
            <td>
              <v-chip
                class="soft-chip"
                size="x-small"
                :color="stop.stop_status === 'delivered' ? 'success' : 'primary'"
                variant="text"
              >
                {{ stop.stop_status === 'delivered' ? 'Доставлено' : 'В плане' }}
              </v-chip>
            </td>
          </tr>
        </tbody>
      </v-table>
    </article>
  </section>
</template>

<script setup lang="ts">
import { useSolverStore } from './useSolverStore'
import { useErpStore } from './useErpStore'
import {
  formatFreshness,
  formatKg,
  formatKm,
  formatMinutes,
  formatRub,
} from '@/shared/utils/format'
import { freshnessLevel } from '@/shared/utils/freshness'

const solver = useSolverStore()
const erp = useErpStore()

function colorOf(truckId: number): string {
  return solver.routeColorByTruck.get(truckId) ?? '#6d28d9'
}

function clientName(clientId: number): string {
  return erp.clientById.get(clientId)?.name ?? `Покупатель №${clientId}`
}

function productName(productId: number): string {
  return erp.productById.get(productId)?.name ?? `Урожай №${productId}`
}

/** Клиент с подъездом по грунтовке — это замедление рейса и потеря сохранности. */
function isDirt(clientId: number): boolean {
  return erp.clientById.get(clientId)?.road_type === 'dirt'
}
</script>

<style scoped lang="scss">
.plan {
  display: grid;
  gap: 12px;
}

.plan-title {
  margin: 0;
  font-size: 15px;
}

.route-card {
  display: grid;
  gap: 6px;
  padding: 12px;
  overflow-x: auto;
}

/* Таблица рейса не сжимается: колонки держатся в один ряд, скролл — по карточке. */
.excel-table :deep(.v-table__wrapper > table) {
  min-width: 820px;
}

.route-head {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 8px;
}

.route-swatch {
  width: 14px;
  height: 14px;
  border-radius: 4px;
}

.route-name {
  font-weight: 600;
}

.route-meta {
  margin-left: auto;
  font-size: 12px;
  color: #5b5175;
}

/* Подсветка строк по свежести: цвет не единственный носитель — в ячейке есть значение. */
.row-warning {
  background: rgba(245, 158, 11, 0.12);
}

.row-error {
  background: rgba(190, 18, 60, 0.12);
}

.dirt-note {
  display: inline-flex;
  align-items: center;
  gap: 3px;
  margin-left: 6px;
  font-size: 11px;
  color: #8a5a12;
  white-space: nowrap;
}
</style>

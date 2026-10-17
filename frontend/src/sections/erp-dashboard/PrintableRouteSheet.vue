<template>
  <section v-if="solver.plan" class="sheet print-root" aria-label="Печатный маршрутный лист">
    <header class="sheet-head">
      <div>
        <h1 class="sheet-title">Маршрутный лист</h1>
        <p class="sheet-sub">Расчёт №{{ runId }} · {{ printedAtText }}</p>
      </div>
      <div class="sheet-weather">
        <p>{{ weatherText }}</p>
        <p>Машин: {{ solver.routes.length }}</p>
      </div>
    </header>

    <article v-for="route in solver.routes" :key="route.truck_id" class="sheet-route">
      <h2 class="sheet-route-title">
        {{ route.truck_name }}
        <span class="sheet-route-meta">
          {{ formatKm(route.total_distance_km) }} · {{ formatMinutes(route.total_duration_min) }} ·
          {{ formatRub(route.total_cost_rub) }}
        </span>
      </h2>

      <table class="sheet-table">
        <thead>
          <tr>
            <th>№</th>
            <th>Покупатель и адрес</th>
            <th>Дорога</th>
            <th>Урожай</th>
            <th class="num">Вес</th>
            <th class="num">В пути</th>
            <th class="num">Сохранность</th>
            <th class="num">Стоимость</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="stop in route.stops" :key="`${route.truck_id}-${stop.sequence_order}`">
            <td>{{ stop.sequence_order }}</td>
            <td>
              <strong>{{ clientName(stop.client_id) }}</strong>
              <span class="sheet-address">{{ clientAddress(stop.client_id) }}</span>
            </td>
            <td>{{ roadLabel(stop.client_id) }}</td>
            <td>{{ productName(stop.product_id) }}</td>
            <td class="num">{{ formatKg(stop.shipped_kg) }}</td>
            <td class="num">{{ formatMinutes(stop.eta_minutes) }}</td>
            <td class="num">{{ formatFreshness(stop.expected_freshness) }}</td>
            <td class="num">{{ formatRub(stop.trip_leg_cost_rub) }}</td>
          </tr>
        </tbody>
        <tfoot>
          <tr>
            <td colspan="4">Итого по рейсу</td>
            <td class="num">{{ formatKg(truckLoad(route.truck_id)) }}</td>
            <td colspan="3" class="num">
              {{ formatKm(route.total_distance_km) }} · {{ formatRub(route.total_cost_rub) }}
            </td>
          </tr>
        </tfoot>
      </table>

      <div class="sheet-signs">
        <span>Водитель: ______________________</span>
        <span>Диспетчер: ______________________</span>
        <span>Дата: «____» __________ 20____ г.</span>
      </div>
    </article>

    <ul v-if="solver.warnings.length > 0" class="sheet-warnings">
      <li v-for="warning in solver.warnings" :key="warning.code + (warning.order_id ?? '')">
        {{ warning.message }}
      </li>
    </ul>

    <footer class="sheet-foot">AgroLogistix · маршрутный лист по расчёту №{{ runId }}</footer>
  </section>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { useSolverStore } from './useSolverStore'
import { useErpStore } from './useErpStore'
import { useWeatherStore } from './useWeatherStore'
import {
  formatDecimal,
  formatFreshness,
  formatKg,
  formatKm,
  formatMinutes,
  formatRub,
} from '@/shared/utils/format'
import { weatherPreset } from './useWeatherStore'

const solver = useSolverStore()
const erp = useErpStore()
const weather = useWeatherStore()

const runId = computed(() => solver.plan?.run_id ?? '—')
const printedAtText = computed(() => new Date().toLocaleString('ru-RU'))

const weatherText = computed(() => {
  const current = weather.weather
  if (!current) return 'Погода: нет данных'
  const preset = weatherPreset(current.mode)
  const conditions = `${Math.round(current.temperature_c)} °C, осадки ${formatDecimal(current.precipitation_mm)} мм`
  if (preset.simulation)
    return `Симуляция погоды: ${preset.title.replace('Симуляция: ', '')}, ${conditions}`
  return `Фактическая погода: ${conditions}`
})

function clientName(clientId: number): string {
  return erp.clientById.get(clientId)?.name ?? `Покупатель №${clientId}`
}

function clientAddress(clientId: number): string {
  return erp.clientById.get(clientId)?.address ?? ''
}

function roadLabel(clientId: number): string {
  return erp.clientById.get(clientId)?.road_type === 'dirt' ? 'Грунтовка' : 'Асфальт'
}

function productName(productId: number): string {
  return erp.productById.get(productId)?.name ?? `Урожай №${productId}`
}

/** Фактическая загрузка машины: сумма отгружённых кг по её остановкам. */
function truckLoad(truckId: number): number {
  const route = solver.routes.find((item) => item.truck_id === truckId)
  return (route?.stops ?? []).reduce((sum, stop) => sum + stop.shipped_kg, 0)
}
</script>

<!-- Экранные стили минимальны: лист показывается только при печати (см. print.scss). -->
<style scoped lang="scss">
.sheet {
  color: #111;
  background: #fff;
  font-family: var(--font-body);
}

.sheet-table {
  width: 100%;
  border-collapse: collapse;
  font-size: 11px;
}

.sheet-table th,
.sheet-table td {
  padding: 4px 6px;
  border: 1px solid #999;
  text-align: left;
  vertical-align: top;
}

.sheet-table .num {
  text-align: right;
  white-space: nowrap;
}

.sheet-address {
  display: block;
  font-size: 10px;
  color: #444;
}
</style>

<template>
  <div class="tab-body">
    <header class="tab-header">
      <div>
        <h2 class="tab-title">Автопарк</h2>
        <p class="tab-subtitle">
          Рефрижератор, допуск к грунтовке и состояние машины. Сломанные машины исключаются из
          расчёта.
        </p>
      </div>
      <v-chip class="soft-chip" size="small" prepend-icon="mdi-truck-outline">
        {{ erp.activeTrucks.length }} в строю
      </v-chip>
    </header>

    <StatePanel
      :status="erp.panelStatus"
      :error-text="erp.errorMessage"
      loading-text="Загружаем автопарк…"
      empty-title="Машин пока нет"
      empty-icon="mdi-truck-remove-outline"
      @retry="reload"
    >
      <div class="summary-row">
        <div class="summary-card neu-inset">
          <span class="summary-label">В строю</span>
          <span class="summary-value mono">{{ erp.activeTrucks.length }}</span>
          <span class="summary-hint">{{ formatKg(erp.activeCapacityKg) }} вместимости</span>
        </div>
        <div class="summary-card neu-inset">
          <span class="summary-label">Сломано</span>
          <span class="summary-value mono">{{ erp.brokenTrucks.length }}</span>
          <span class="summary-hint">исключены из расчёта</span>
        </div>
        <div class="summary-card neu-inset">
          <span class="summary-label">Рефрижераторы</span>
          <span class="summary-value mono">{{ erp.reeferTrucks.length }}</span>
          <span class="summary-hint">контроль температуры</span>
        </div>
        <div class="summary-card neu-inset">
          <span class="summary-label">Проходимые</span>
          <span class="summary-value mono">{{ erp.dirtCapableTrucks.length }}</span>
          <span class="summary-hint">допуск к грунтовке</span>
        </div>
      </div>

      <v-table density="comfortable" class="erp-table">
        <thead>
          <tr>
            <th scope="col">Машина</th>
            <th scope="col">База</th>
            <th scope="col" class="text-right">Вместимость</th>
            <th scope="col" class="text-right">Скорость</th>
            <th scope="col" class="text-right">₽/км</th>
            <th scope="col" class="text-right">Фикс. рейс</th>
            <th scope="col">Оснащение</th>
            <th scope="col">Статус</th>
          </tr>
        </thead>
        <tbody>
          <tr
            v-for="truck in erp.trucks"
            :key="truck.id"
            :class="{ 'row-broken': truck.status === 'broken' }"
          >
            <td>
              <span class="font-weight-medium">{{ truck.name }}</span>
              <span class="cell-note mono">{{ truck.plate_number }}</span>
            </td>
            <td>{{ erp.warehouseById.get(truck.warehouse_id)?.name ?? '—' }}</td>
            <td class="text-right mono">{{ formatKg(truck.capacity_kg) }}</td>
            <td class="text-right mono">{{ formatSpeed(truck.cruise_speed_kmh) }}</td>
            <td class="text-right mono">{{ formatRub(truck.cost_per_km_rub) }}</td>
            <td class="text-right mono">{{ formatRub(truck.fixed_trip_cost_rub) }}</td>
            <td>
              <div class="tag-row">
                <v-chip
                  size="small"
                  class="soft-chip"
                  :prepend-icon="truck.has_reefer ? 'mdi-snowflake' : 'mdi-weather-sunny'"
                >
                  {{ truck.has_reefer ? 'Реф' : 'Без рефа' }}
                </v-chip>
                <v-chip
                  size="small"
                  class="soft-chip"
                  :prepend-icon="truck.can_use_dirt ? 'mdi-image-filter-hdr' : 'mdi-highway'"
                >
                  {{ truck.can_use_dirt ? 'Грунт' : 'Только асфальт' }}
                </v-chip>
              </div>
            </td>
            <td>
              <v-btn
                size="small"
                variant="tonal"
                :color="truck.status === 'active' ? 'success' : 'error'"
                :prepend-icon="
                  truck.status === 'active' ? 'mdi-check-circle-outline' : 'mdi-wrench-outline'
                "
                :loading="erp.isPending(`truck:${truck.id}`)"
                :aria-pressed="truck.status === 'active'"
                :aria-label="`${truck.name}: переключить состояние машины`"
                @click="toggleTruck(truck)"
              >
                {{ truck.status === 'active' ? 'В строю' : 'Сломана' }}
              </v-btn>
            </td>
          </tr>
        </tbody>
      </v-table>

      <p class="tab-footnote">
        Сломанная машина сохраняется на сервере (<span class="mono"
          >PATCH /erp/trucks/&#123;id&#125;</span
        >) и исключается из расчёта поставок.
      </p>
    </StatePanel>
  </div>
</template>

<script setup lang="ts">
import StatePanel from '@/shared/components/StatePanel.vue'
import { useErpStore } from './useErpStore'
import { formatKg, formatRub, formatSpeed } from '@/shared/utils/format'
import type { Truck, TruckStatus } from '@/shared/types/domain'

const erp = useErpStore()

function reload(): void {
  void erp.loadState({ force: true })
}

function toggleTruck(truck: Truck): void {
  const status: TruckStatus = truck.status === 'active' ? 'broken' : 'active'
  void erp.updateTruck(truck.id, { status })
}
</script>

<style scoped lang="scss">
.tab-body {
  display: grid;
  /* minmax(0,1fr) не даёт таблице с min-width растянуть всю панель. */
  grid-template-columns: minmax(0, 1fr);
  gap: 16px;
}

.tab-header {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 12px;
}

/* Заголовок сжимается и переносится, чип сохраняет целую ширину. */
.tab-header > div {
  flex: 1 1 auto;
  min-width: 0;
}

.tab-header :deep(.v-chip) {
  flex: 0 0 auto;
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

.summary-row {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(150px, 1fr));
  gap: 12px;
  margin-bottom: 16px;
}

.summary-card {
  display: grid;
  gap: 2px;
  padding: 12px 14px;
}

.summary-label {
  font-size: 13px;
  font-weight: 600;
}

.summary-value {
  font-size: 18px;
}

.summary-hint {
  font-size: 12px;
  color: #5b5175;
}

.erp-table {
  max-width: 100%;
  border: var(--neu-border);
  border-radius: var(--neu-radius-sm);
  background: var(--neu-bg);
}

/* Компактные ячейки: при узкой левой панели влезает больше колонок. */
.erp-table :deep(th),
.erp-table :deep(td) {
  padding-inline: 10px;
}

.erp-table :deep(thead th) {
  position: sticky;
  top: 0;
  background: #e7dff6;
  font-weight: 600;
  white-space: nowrap;
}

.erp-table :deep(tbody tr:nth-child(even)) {
  background: rgba(231, 223, 246, 0.45);
}

/* Таблица шире панели — даём горизонтальный скролл вместо сжатия колонок. */
.erp-table :deep(.v-table__wrapper > table) {
  min-width: 860px;
}

.row-broken {
  opacity: 0.72;
}

.cell-note {
  display: block;
  font-size: 12px;
  color: #5b5175;
}

.tag-row {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}

.tab-footnote {
  margin: 12px 0 0;
  font-size: 12px;
  color: #5b5175;
}
</style>

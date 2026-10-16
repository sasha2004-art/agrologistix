<template>
  <div class="tab-body">
    <header class="tab-header">
      <div>
        <h2 class="tab-title">Склады и остатки</h2>
        <p class="tab-subtitle">Мульти-склады Калужской области и доступные партии по культурам.</p>
      </div>
      <v-chip class="soft-chip" size="small" prepend-icon="mdi-warehouse">
        {{ erp.warehouses.length }} склада
      </v-chip>
    </header>

    <StatePanel
      :status="erp.panelStatus"
      :error-text="erp.errorMessage"
      loading-text="Загружаем склады и остатки…"
      empty-title="Складов пока нет"
      empty-icon="mdi-warehouse"
      @retry="reload"
    >
      <div class="summary-row">
        <div v-for="row in erp.stockMatrix" :key="row.warehouse.id" class="summary-card neu-inset">
          <span class="summary-label">{{ row.warehouse.name }}</span>
          <span class="summary-value mono">{{ formatKg(row.total_kg) }}</span>
          <span class="summary-hint">{{
            row.warehouse.is_active ? 'склад активен' : 'склад отключён'
          }}</span>
        </div>
      </div>

      <v-table density="comfortable" class="erp-table">
        <thead>
          <tr>
            <th scope="col">Склад</th>
            <th v-for="product in erp.products" :key="product.id" scope="col" class="text-right">
              {{ product.name }}
              <span class="cell-code mono">{{ product.code }}</span>
            </th>
            <th scope="col" class="text-right">Итого</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="row in erp.stockMatrix" :key="row.warehouse.id">
            <td>
              <span class="font-weight-medium">{{ row.warehouse.name }}</span>
              <span class="cell-note">{{ row.warehouse.address }}</span>
            </td>
            <td
              v-for="cell in row.cells"
              :key="cell.product.id"
              class="text-right mono"
              :class="{ 'value-empty': cell.available_kg === 0 }"
            >
              {{ formatKg(cell.available_kg) }}
            </td>
            <td class="text-right mono font-weight-medium">{{ formatKg(row.total_kg) }}</td>
          </tr>
        </tbody>
      </v-table>

      <p class="tab-footnote">
        Остаток можно будет изменить через
        <span class="mono">PATCH /erp/stocks/&#123;id&#125;</span>
        на Day 4.
      </p>
    </StatePanel>
  </div>
</template>

<script setup lang="ts">
import StatePanel from '@/shared/components/StatePanel.vue'
import { useErpStore } from './useErpStore'
import { formatKg } from '@/shared/utils/format'

const erp = useErpStore()

function reload(): void {
  void erp.loadState({ force: true })
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
  min-width: 560px;
}

.cell-code,
.cell-note {
  display: block;
  font-size: 12px;
  color: #5b5175;
}

.value-empty {
  color: #5b5175;
}

.tab-footnote {
  margin: 12px 0 0;
  font-size: 12px;
  color: #5b5175;
}
</style>

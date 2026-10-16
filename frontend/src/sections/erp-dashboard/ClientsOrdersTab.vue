<template>
  <div class="tab-body">
    <header class="tab-header">
      <div>
        <h2 class="tab-title">Заявки B2B-клиентов</h2>
        <p class="tab-subtitle">
          Объём, закупочная цена и тип подъездной дороги. Статус меняется по
          <span class="mono">order_id</span>.
        </p>
      </div>
      <v-chip class="soft-chip" size="small" prepend-icon="mdi-clipboard-list-outline">
        {{ erp.orderRows.length }} заявок
      </v-chip>
    </header>

    <StatePanel
      :status="erp.panelStatus"
      :error-text="erp.errorMessage"
      loading-text="Загружаем заявки клиентов…"
      empty-title="Заявок пока нет"
      empty-icon="mdi-clipboard-text-off-outline"
      @retry="reload"
    >
      <div class="summary-row">
        <div class="summary-card neu-inset">
          <span class="summary-label">В работе</span>
          <span class="summary-value mono">{{ erp.pendingOrders.length }}</span>
          <span class="summary-hint">{{ formatKg(erp.pendingVolumeKg) }}</span>
        </div>
        <div class="summary-card neu-inset">
          <span class="summary-label">Доставлено</span>
          <span class="summary-value mono">{{ erp.deliveredOrders.length }}</span>
          <span class="summary-hint">заявок закрыто</span>
        </div>
        <div class="summary-card neu-inset">
          <span class="summary-label">Выручка в работе</span>
          <span class="summary-value mono">{{ formatRub(erp.pendingRevenueRub) }}</span>
          <span class="summary-hint">объём × цена</span>
        </div>
        <div class="summary-card neu-inset">
          <span class="summary-label">Точки на грунте</span>
          <span class="summary-value mono">{{ erp.dirtClients.length }}</span>
          <span class="summary-hint">нужен вездеход</span>
        </div>
      </div>

      <v-table density="comfortable" class="erp-table">
        <thead>
          <tr>
            <th scope="col">№</th>
            <th scope="col">Клиент</th>
            <th scope="col">Культура</th>
            <th scope="col" class="text-right">Объём</th>
            <th scope="col" class="text-right">Цена, ₽/кг</th>
            <th scope="col" class="text-right">Штраф</th>
            <th scope="col">Дорога</th>
            <th scope="col">Статус</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="row in erp.orderRows" :key="row.order.id">
            <td class="mono">{{ row.order.id }}</td>
            <td>
              <span class="font-weight-medium">{{ row.client.name }}</span>
              <span class="cell-note">{{ row.client.address }}</span>
            </td>
            <td>{{ row.product.name }}</td>
            <td class="text-right mono">{{ formatKg(row.order.requested_kg) }}</td>
            <td class="text-right mono">{{ formatRub(row.order.purchase_price_rub) }}</td>
            <td class="text-right mono">{{ formatRub(row.order.unmet_penalty_rub) }}</td>
            <td>
              <v-chip
                class="soft-chip"
                size="small"
                :prepend-icon="row.client.road_type === 'dirt' ? 'mdi-road-variant' : 'mdi-road'"
              >
                {{ row.client.road_type === 'dirt' ? 'Грунтовка' : 'Асфальт' }}
              </v-chip>
            </td>
            <td>
              <v-chip
                size="small"
                variant="tonal"
                :color="row.order.delivery_status === 'delivered' ? 'success' : 'warning'"
                :prepend-icon="
                  row.order.delivery_status === 'delivered'
                    ? 'mdi-check-circle-outline'
                    : 'mdi-clock-outline'
                "
              >
                {{ row.order.delivery_status === 'delivered' ? 'Доставлено' : 'В работе' }}
              </v-chip>
            </td>
          </tr>
        </tbody>
      </v-table>

      <p class="tab-footnote">
        Пока таблица только читает состояние. Редактирование цены и отметка «Доставлено» — Day 4
        (<span class="mono">PATCH /erp/orders/&#123;id&#125;</span>).
      </p>
    </StatePanel>
  </div>
</template>

<script setup lang="ts">
import StatePanel from '@/shared/components/StatePanel.vue'
import { useErpStore } from './useErpStore'
import { formatKg, formatRub } from '@/shared/utils/format'

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
  min-width: 740px;
}

.cell-note {
  display: block;
  font-size: 12px;
  color: #5b5175;
}

.tab-footnote {
  margin: 12px 0 0;
  font-size: 12px;
  color: #5b5175;
}
</style>

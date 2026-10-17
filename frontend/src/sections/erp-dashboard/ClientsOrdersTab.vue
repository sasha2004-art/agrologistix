<template>
  <div class="tab-body">
    <header class="tab-header">
      <div>
        <h2 class="tab-title">Заказы покупателей</h2>
        <p class="tab-subtitle">
          Объём, цена продажи и дорога к покупателю. Изменения сохраняются сразу и учитываются в
          следующем расчёте.
        </p>
      </div>
      <v-chip class="soft-chip" size="small" prepend-icon="mdi-clipboard-list-outline">
        {{ erp.orderRows.length }} заказов
      </v-chip>
    </header>

    <StatePanel
      :status="erp.panelStatus"
      :error-text="erp.errorMessage"
      loading-text="Загружаем заказы покупателей…"
      empty-title="Заказов пока нет"
      empty-icon="mdi-clipboard-text-off-outline"
      @retry="reload"
    >
      <v-table density="comfortable" class="erp-table">
        <thead>
          <tr>
            <th scope="col">№</th>
            <th scope="col">Покупатель</th>
            <th scope="col">Культура</th>
            <th scope="col" class="text-right">Объём</th>
            <th scope="col" class="text-right">Цена, ₽/кг</th>
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
            <td class="text-right mono">
              {{ formatKg(row.order.requested_kg) }}
              <span
                v-if="partialDelivery(row.order.delivered_kg, row.order.requested_kg)"
                class="cell-note"
              >
                отгружено {{ formatKg(row.order.delivered_kg) }}, остаток
                {{ formatKg(row.order.requested_kg - row.order.delivered_kg) }}
              </span>
            </td>
            <td class="text-right">
              <EditableNumberField
                :model-value="row.order.purchase_price_rub"
                :min="1"
                :step="10"
                suffix="₽"
                :loading="erp.isPending(`order:${row.order.id}`)"
                :aria-label="`Заказ №${row.order.id}: цена за кг в рублях`"
                @commit="(value) => savePrice(row, value)"
              />
            </td>
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
              <v-btn
                size="small"
                variant="tonal"
                :color="row.order.delivery_status === 'delivered' ? 'success' : 'warning'"
                :prepend-icon="
                  row.order.delivery_status === 'delivered'
                    ? 'mdi-check-circle-outline'
                    : 'mdi-clock-outline'
                "
                :loading="erp.isPending(`order:${row.order.id}`)"
                :aria-pressed="row.order.delivery_status === 'delivered'"
                :aria-label="`Заказ №${row.order.id}: переключить статус доставки`"
                @click="toggleDelivered(row)"
              >
                {{ row.order.delivery_status === 'delivered' ? 'Доставлено' : 'В работе' }}
              </v-btn>
            </td>
          </tr>
        </tbody>
      </v-table>

    </StatePanel>
  </div>
</template>

<script setup lang="ts">
import StatePanel from '@/shared/components/StatePanel.vue'
import EditableNumberField from '@/shared/components/EditableNumberField.vue'
import { useErpStore, type OrderRow } from './useErpStore'
import { formatKg } from '@/shared/utils/format'
import type { DeliveryStatus } from '@/shared/types/domain'

const erp = useErpStore()

function reload(): void {
  void erp.loadState({ force: true })
}

function savePrice(row: OrderRow, value: number): void {
  void erp.updateOrder(row.order.id, { purchase_price_rub: value })
}

function toggleDelivered(row: OrderRow): void {
  const next: DeliveryStatus = row.order.delivery_status === 'delivered' ? 'pending' : 'delivered'
  void erp.updateOrder(row.order.id, { delivery_status: next })
}

/** A partially shipped order keeps the leftover demand after PATCH delivered. */
function partialDelivery(deliveredKg: number, requestedKg: number): boolean {
  return deliveredKg > 0 && deliveredKg < requestedKg
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
  min-width: 900px;
}

.cell-note {
  display: block;
  font-size: 12px;
  color: #5b5175;
}
</style>

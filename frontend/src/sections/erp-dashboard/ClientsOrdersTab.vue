<template>
  <div class="tab-body">
    <header class="tab-header">
      <div>
        <h2 class="tab-title">Заказы покупателей</h2>
      </div>
      <div class="header-actions">
        <v-chip class="soft-chip" size="small" prepend-icon="mdi-clipboard-list-outline">
          {{ erp.orderRows.length }} заказов
        </v-chip>
        <v-btn
          variant="tonal"
          color="primary"
          size="small"
          prepend-icon="mdi-store-plus-outline"
          @click="clientOpen = true"
        >
          Магазин
        </v-btn>
        <v-btn
          variant="tonal"
          color="primary"
          size="small"
          prepend-icon="mdi-plus"
          @click="orderOpen = true"
        >
          Заказ
        </v-btn>
      </div>
    </header>

    <StatePanel
      :status="erp.panelStatus"
      :error-text="erp.errorMessage"
      loading-text="Загружаем заказы покупателей…"
      empty-title="Заказов пока нет"
      empty-icon="mdi-clipboard-text-off-outline"
      @retry="reload"
    >
      <v-table density="comfortable" class="excel-table">
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
              <!-- Цена за кг влияет на выручку, потери и выбор партии в расчёте. -->
              <EditableNumberField
                :model-value="row.order.purchase_price_rub"
                :min="MIN_PRICE_RUB"
                :step="0.5"
                suffix="₽"
                :loading="erp.isPending(`order:${row.order.id}`)"
                :aria-label="`Заказ №${row.order.id}, ${row.product.name}: цена за кг`"
                @commit="(value) => savePrice(row, value)"
              />
            </td>
            <td>
              <!-- Дорога только иконкой: расшифровка — в подсказке и aria-label. -->
              <v-icon
                :icon="row.client.road_type === 'dirt' ? 'mdi-image-filter-hdr' : 'mdi-highway'"
                :color="row.client.road_type === 'dirt' ? 'warning' : undefined"
                size="20"
                :aria-label="row.client.road_type === 'dirt' ? 'Грунтовка' : 'Асфальт'"
              >
                <v-tooltip activator="parent" location="top">
                  {{ row.client.road_type === 'dirt' ? 'Грунтовка' : 'Асфальт' }}
                </v-tooltip>
              </v-icon>
            </td>
            <td>
              <v-menu location="bottom end">
                <template #activator="{ props: menuProps }">
                  <v-btn
                    v-bind="menuProps"
                    size="small"
                    variant="tonal"
                    :color="statusMeta(row.order.delivery_status).color"
                    :prepend-icon="statusMeta(row.order.delivery_status).icon"
                    :loading="
                      erp.isPending(`order:${row.order.id}`) || assignment.isPending(row.order.id)
                    "
                    :aria-label="`Заказ №${row.order.id}: изменить этап поставки`"
                  >
                    {{ statusMeta(row.order.delivery_status).label }}
                  </v-btn>
                </template>
                <v-list density="compact" min-width="190">
                  <v-list-item
                    v-for="option in STATUS_OPTIONS"
                    :key="option.value"
                    :prepend-icon="option.icon"
                    :title="option.label"
                    :active="row.order.delivery_status === option.value"
                    @click="setStatus(row, option.value)"
                  />
                </v-list>
              </v-menu>
              <!-- Подобранные маршрут и машина показываются у заявок «В работе». -->
              <span v-if="assignmentNote(row)" class="cell-note assignment-note">
                {{ assignmentNote(row) }}
              </span>
            </td>
          </tr>
        </tbody>
      </v-table>
    </StatePanel>

    <CreateClientDialog v-model="clientOpen" />
    <CreateOrderDialog v-model="orderOpen" />
  </div>
</template>

<script setup lang="ts">
import { ref, watch } from 'vue'
import StatePanel from '@/shared/components/StatePanel.vue'
import EditableNumberField from '@/shared/components/EditableNumberField.vue'
import CreateClientDialog from './create/CreateClientDialog.vue'
import CreateOrderDialog from './create/CreateOrderDialog.vue'
import { useErpStore, type OrderRow } from './useErpStore'
import { assignmentSummary, useAssignmentStore } from './useAssignmentStore'
import { formatKg } from '@/shared/utils/format'
import type { DeliveryStatus } from '@/shared/types/domain'

const erp = useErpStore()
const clientOpen = ref(false)
const orderOpen = ref(false)
const assignment = useAssignmentStore()

/** Заказ с нулевой ценой не пройдёт валидацию PATCH (`purchase_price_rub > 0`). */
const MIN_PRICE_RUB = 0.01

function reload(): void {
  void erp.loadState({ force: true })
}

function savePrice(row: OrderRow, value: number): void {
  void erp.updateOrder(row.order.id, { purchase_price_rub: value })
}

/** Три этапа поставки: заявка ждёт плана → груз в пути → доставлено. */
const STATUS_OPTIONS: { value: DeliveryStatus; label: string; icon: string; color: string }[] = [
  { value: 'pending', label: 'В плане', icon: 'mdi-calendar-clock', color: 'warning' },
  { value: 'in_progress', label: 'В работе', icon: 'mdi-truck-fast-outline', color: 'info' },
  { value: 'delivered', label: 'Доставлено', icon: 'mdi-check-circle-outline', color: 'success' },
]

function statusMeta(status: DeliveryStatus) {
  return STATUS_OPTIONS.find((option) => option.value === status) ?? STATUS_OPTIONS[0]
}

async function setStatus(row: OrderRow, status: DeliveryStatus): Promise<void> {
  if (status === 'in_progress') {
    // Повторный выбор «В работе» пересобирает фиксацию: маршрут на карте
    // появится даже у заявки, взятой в работу без подбора.
    if (!(await assignment.assign(row.order.id))) return
    if (row.order.delivery_status === 'in_progress') return
  }
  if (row.order.delivery_status === status) return
  void erp.updateOrder(row.order.id, { delivery_status: status })
}

/**
 * Заявки «В работе» без фиксации получают подобранный маршрут автоматически:
 * так пунктирная линия появляется и у заявок, взятых в работу до подбора.
 */
watch(
  () =>
    erp.orderRows
      .filter((row) => row.order.delivery_status === 'in_progress')
      .map((row) => row.order.id),
  (orderIds) => {
    void assignment.syncMissing(orderIds)
  },
  { immediate: true },
)

/** Строка с подобранным вариантом у заявки, взятой «В работе». */
function assignmentNote(row: OrderRow): string {
  if (row.order.delivery_status !== 'in_progress') return ''
  const picked = assignment.forOrder(row.order.id)
  return picked ? `Оптимально: ${assignmentSummary(picked)}` : ''
}

/** A partially shipped order keeps the leftover demand after PATCH delivered. */
function partialDelivery(deliveredKg: number, requestedKg: number): boolean {
  return deliveredKg > 0 && deliveredKg < requestedKg
}
</script>

<style scoped lang="scss">
.header-actions {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 8px;
}

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

/* Таблица шире панели — даём горизонтальный скролл вместо сжатия колонок.
   Запас под редактируемое поле цены (150 px) и подпись «отгружено/остаток». */
.excel-table :deep(.v-table__wrapper > table) {
  min-width: 1020px;
}

.cell-note {
  display: block;
  font-size: 12px;
  color: #5b5175;
}

.assignment-note {
  max-width: 260px;
  white-space: normal;
}
</style>

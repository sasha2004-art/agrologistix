<template>
  <CreateDialogShell
    v-model="open"
    title="Партия на складе"
    subtitle="Новая партия товара: сколько килограммов есть и насколько свежий урожай"
    :submitting="submitting"
    :error="error"
    @submit="submit"
  >
    <v-select
      v-model="warehouseId"
      :items="warehouseOptions"
      item-title="title"
      item-value="value"
      label="Склад"
      density="comfortable"
      variant="outlined"
      hide-details
    />
    <v-select
      v-model="productId"
      :items="productOptions"
      item-title="title"
      item-value="value"
      label="Товар"
      density="comfortable"
      variant="outlined"
      hide-details
    />
    <div class="two-col">
      <v-text-field
        v-model.number="availableKg"
        type="number"
        step="100"
        min="0"
        label="Доступно, кг"
        density="comfortable"
        variant="outlined"
        hide-details
      />
      <v-text-field
        v-model.number="freshness"
        type="number"
        step="0.01"
        min="0.5"
        max="1"
        label="Свежесть партии (0,5 … 1)"
        density="comfortable"
        variant="outlined"
        hide-details
      />
    </div>
    <!-- Занятые пары «склад + товар» показываем заранее: иначе сервер вернёт 409. -->
    <p v-if="takenPairs.length > 0" class="taken-note">
      Уже есть партии: {{ takenPairs.join('; ') }}. Для них меняйте остаток, а не создавайте строку.
    </p>
  </CreateDialogShell>
</template>

<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import CreateDialogShell from './CreateDialogShell.vue'
import { useErpCreateStore } from '../useErpCreateStore'
import { useErpStore } from '../useErpStore'

const open = defineModel<boolean>({ default: false })
const erpCreate = useErpCreateStore()
const erp = useErpStore()

const warehouseOptions = computed(() =>
  erp.warehouses.map((warehouse) => ({ title: warehouse.name, value: warehouse.id })),
)
const productOptions = computed(() =>
  erp.products.map((product) => ({ title: product.name, value: product.id })),
)

const takenPairs = computed(() =>
  erp.stocks.map((stock) => {
    const warehouse =
      erp.warehouseById.get(stock.warehouse_id)?.name ?? `Склад №${stock.warehouse_id}`
    const product = erp.productById.get(stock.product_id)?.name ?? `Товар №${stock.product_id}`
    return `${warehouse} — ${product}`
  }),
)

const warehouseId = ref<number | null>(null)
const productId = ref<number | null>(null)
const availableKg = ref(1000)
const freshness = ref(1)
const submitting = ref(false)
const error = ref<string | null>(null)

const valid = computed(
  () =>
    warehouseId.value !== null &&
    productId.value !== null &&
    availableKg.value >= 0 &&
    freshness.value >= 0.5 &&
    freshness.value <= 1,
)

watch(open, (isOpen) => {
  if (!isOpen) return
  error.value = null
  if (warehouseId.value === null) warehouseId.value = erp.warehouses[0]?.id ?? null
  if (productId.value === null) productId.value = erp.products[0]?.id ?? null
})

async function submit(): Promise<void> {
  if (!valid.value || submitting.value || warehouseId.value === null || productId.value === null) {
    return
  }
  submitting.value = true
  error.value = null
  const ok = await erpCreate.addStock({
    warehouse_id: warehouseId.value,
    product_id: productId.value,
    available_kg: availableKg.value,
    initial_freshness: freshness.value,
  })
  submitting.value = false
  if (!ok) {
    error.value = 'Партия не добавлена: возможно, у этого склада уже есть партия такого товара.'
    return
  }
  open.value = false
  availableKg.value = 1000
  freshness.value = 1
}
</script>

<style scoped lang="scss">
.two-col {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 10px;
}

.taken-note {
  margin: 0;
  font-size: 11px;
  color: #5b5175;
}
</style>

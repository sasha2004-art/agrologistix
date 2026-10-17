<template>
  <CreateDialogShell
    v-model="open"
    title="Новый заказ"
    subtitle="Заказ появится со статусом «В плане» и сразу участвует в следующем расчёте"
    :submitting="submitting"
    :error="error"
    @submit="submit"
  >
    <v-select
      v-model="clientId"
      :items="clientOptions"
      item-title="title"
      item-value="value"
      label="Магазин"
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
        v-model.number="requestedKg"
        type="number"
        step="50"
        min="1"
        label="Объём, кг"
        density="comfortable"
        variant="outlined"
        hide-details
      />
      <v-text-field
        v-model.number="pricePerKg"
        type="number"
        step="10"
        min="1"
        label="Цена, ₽/кг"
        density="comfortable"
        variant="outlined"
        hide-details
      />
    </div>
    <v-text-field
      v-model.number="penalty"
      type="number"
      step="10"
      min="0"
      label="Неустойка за недовоз, ₽/кг"
      density="comfortable"
      variant="outlined"
      hide-details
    />
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

const clientOptions = computed(() =>
  erp.clients.map((client) => ({ title: client.name, value: client.id })),
)
const productOptions = computed(() =>
  erp.products.map((product) => ({ title: product.name, value: product.id })),
)

const clientId = ref<number | null>(null)
const productId = ref<number | null>(null)
const requestedKg = ref(500)
const pricePerKg = ref(120)
const penalty = ref(0)
const submitting = ref(false)
const error = ref<string | null>(null)

const valid = computed(
  () =>
    clientId.value !== null &&
    productId.value !== null &&
    requestedKg.value > 0 &&
    pricePerKg.value > 0 &&
    penalty.value >= 0,
)

// Подставляем первых доступных: иначе форма открывается пустой и это выглядит как поломка.
watch(open, (isOpen) => {
  if (!isOpen) return
  error.value = null
  if (clientId.value === null) clientId.value = erp.clients[0]?.id ?? null
  if (productId.value === null) productId.value = erp.products[0]?.id ?? null
})

async function submit(): Promise<void> {
  if (!valid.value || submitting.value || clientId.value === null || productId.value === null)
    return
  submitting.value = true
  error.value = null
  const ok = await erpCreate.addOrder({
    client_id: clientId.value,
    product_id: productId.value,
    requested_kg: requestedKg.value,
    purchase_price_rub: pricePerKg.value,
    unmet_penalty_rub: penalty.value,
  })
  submitting.value = false
  if (!ok) {
    error.value = 'Заказ не создан: проверьте магазин, товар и числа.'
    return
  }
  open.value = false
  requestedKg.value = 500
}
</script>

<style scoped lang="scss">
.two-col {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 10px;
}
</style>

<template>
  <CreateDialogShell
    v-model="open"
    title="Новый товар"
    subtitle="Культура попадает в библиотеку и становится доступной в заказах и на складах"
    :submitting="submitting"
    :error="error"
    @submit="submit"
  >
    <v-text-field
      v-model="code"
      label="Код"
      density="comfortable"
      variant="outlined"
      hide-details
    />
    <v-text-field
      v-model="name"
      label="Название"
      density="comfortable"
      variant="outlined"
      hide-details
    />
    <v-text-field
      v-model.number="spoilage"
      type="number"
      step="0.005"
      min="0.001"
      max="1"
      label="Потеря свежести за час (0,02 … 0,08)"
      density="comfortable"
      variant="outlined"
      hide-details
    />
    <v-text-field
      v-model.number="optimalTemp"
      type="number"
      step="0.5"
      label="Оптимальная температура, °C"
      density="comfortable"
      variant="outlined"
      hide-details
    />
    <v-text-field
      v-model.number="cost"
      type="number"
      step="10"
      min="1"
      label="Себестоимость, ₽/кг"
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

const open = defineModel<boolean>({ default: false })
const erpCreate = useErpCreateStore()

const code = ref('')
const name = ref('')
const spoilage = ref(0.04)
const optimalTemp = ref(6)
const cost = ref(120)
const submitting = ref(false)
const error = ref<string | null>(null)

const valid = computed(
  () =>
    code.value.trim().length > 0 &&
    name.value.trim().length > 0 &&
    spoilage.value > 0 &&
    spoilage.value <= 1 &&
    cost.value > 0,
)

watch(open, (isOpen) => {
  if (isOpen) error.value = null
})

async function submit(): Promise<void> {
  if (!valid.value || submitting.value) return
  submitting.value = true
  error.value = null
  const ok = await erpCreate.addProduct({
    code: code.value.trim(),
    name: name.value.trim(),
    base_spoilage_rate: spoilage.value,
    optimal_temp_c: optimalTemp.value,
    base_cost_rub: cost.value,
  })
  submitting.value = false
  if (!ok) {
    error.value = 'Товар не добавлен: проверьте код (он должен быть уникальным) и числа.'
    return
  }
  open.value = false
  code.value = ''
  name.value = ''
}
</script>

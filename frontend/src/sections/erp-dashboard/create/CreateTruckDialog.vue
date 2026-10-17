<template>
  <CreateDialogShell
    v-model="open"
    title="Новая машина"
    subtitle="Машина сразу участвует в расчёте: база, вместимость, стоимость километра и оснащение"
    :submitting="submitting"
    :error="error"
    @submit="submit"
  >
    <div class="two-col">
      <v-text-field
        v-model="name"
        label="Название"
        density="comfortable"
        variant="outlined"
        hide-details
      />
      <v-text-field
        v-model="plateNumber"
        label="Госномер"
        density="comfortable"
        variant="outlined"
        hide-details
      />
    </div>
    <v-select
      v-model="warehouseId"
      :items="warehouseOptions"
      item-title="title"
      item-value="value"
      label="База (склад)"
      density="comfortable"
      variant="outlined"
      hide-details
    />
    <div class="two-col">
      <v-text-field
        v-model.number="capacityKg"
        type="number"
        step="500"
        min="1"
        label="Вместимость, кг"
        density="comfortable"
        variant="outlined"
        hide-details
      />
      <v-text-field
        v-model.number="speedKmh"
        type="number"
        step="5"
        min="1"
        max="120"
        label="Скорость, км/ч"
        density="comfortable"
        variant="outlined"
        hide-details
      />
    </div>
    <div class="two-col">
      <v-text-field
        v-model.number="costPerKm"
        type="number"
        step="1"
        min="0"
        label="₽ за километр"
        density="comfortable"
        variant="outlined"
        hide-details
      />
      <v-text-field
        v-model.number="fixedTripCost"
        type="number"
        step="100"
        min="0"
        label="Фикс. за рейс, ₽"
        density="comfortable"
        variant="outlined"
        hide-details
      />
    </div>
    <div class="flags">
      <v-checkbox v-model="hasReefer" label="Рефрижератор" density="compact" hide-details />
      <v-checkbox
        v-model="hasInsulation"
        label="Изотермический кузов"
        density="compact"
        hide-details
      />
      <v-checkbox v-model="canUseDirt" label="Допуск к грунтовке" density="compact" hide-details />
    </div>
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

const name = ref('')
const plateNumber = ref('')
const warehouseId = ref<number | null>(null)
const capacityKg = ref(2000)
const speedKmh = ref(70)
const costPerKm = ref(25)
const fixedTripCost = ref(1000)
const hasReefer = ref(false)
const hasInsulation = ref(false)
const canUseDirt = ref(false)
const submitting = ref(false)
const error = ref<string | null>(null)

const valid = computed(
  () =>
    name.value.trim().length > 0 &&
    plateNumber.value.trim().length > 0 &&
    warehouseId.value !== null &&
    capacityKg.value > 0 &&
    speedKmh.value > 0 &&
    costPerKm.value >= 0 &&
    fixedTripCost.value >= 0,
)

// Первый склад подставляем сразу: без базы машину создать нельзя.
watch(open, (isOpen) => {
  if (!isOpen) return
  error.value = null
  if (warehouseId.value === null) warehouseId.value = erp.warehouses[0]?.id ?? null
})

async function submit(): Promise<void> {
  if (!valid.value || submitting.value || warehouseId.value === null) return
  submitting.value = true
  error.value = null
  const ok = await erpCreate.addTruck({
    name: name.value.trim(),
    plate_number: plateNumber.value.trim(),
    warehouse_id: warehouseId.value,
    capacity_kg: capacityKg.value,
    cruise_speed_kmh: speedKmh.value,
    cost_per_km_rub: costPerKm.value,
    fixed_trip_cost_rub: fixedTripCost.value,
    has_reefer: hasReefer.value,
    has_insulation: hasInsulation.value,
    can_use_dirt: canUseDirt.value,
  })
  submitting.value = false
  if (!ok) {
    error.value = 'Машина не добавлена: проверьте госномер (он должен быть уникальным) и числа.'
    return
  }
  open.value = false
  name.value = ''
  plateNumber.value = ''
}
</script>

<style scoped lang="scss">
.two-col {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 10px;
}

.flags {
  display: flex;
  flex-wrap: wrap;
  gap: 4px 16px;
}
</style>

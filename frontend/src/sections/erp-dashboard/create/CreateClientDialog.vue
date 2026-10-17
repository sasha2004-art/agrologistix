<template>
  <CreateDialogShell
    v-model="open"
    title="Новый магазин"
    subtitle="Точка появится на карте; тип подъезда влияет на время рейса и сохранность урожая"
    :submitting="submitting"
    :error="error"
    @submit="submit"
  >
    <v-text-field
      v-model="name"
      label="Название"
      density="comfortable"
      variant="outlined"
      hide-details
    />
    <v-text-field
      v-model="address"
      label="Адрес"
      density="comfortable"
      variant="outlined"
      hide-details
    />
    <v-select
      v-model="roadType"
      :items="roadOptions"
      item-title="title"
      item-value="value"
      label="Подъезд"
      density="comfortable"
      variant="outlined"
      hide-details
    />
    <div class="coord-row">
      <v-text-field
        v-model.number="lat"
        type="number"
        step="0.0001"
        label="Широта"
        density="comfortable"
        variant="outlined"
        hide-details
      />
      <v-text-field
        v-model.number="lon"
        type="number"
        step="0.0001"
        label="Долгота"
        density="comfortable"
        variant="outlined"
        hide-details
      />
    </div>
  </CreateDialogShell>
</template>

<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import CreateDialogShell from './CreateDialogShell.vue'
import { useErpCreateStore } from '../useErpCreateStore'
import type { RoadType } from '@/shared/types/domain'

const open = defineModel<boolean>({ default: false })
const erpCreate = useErpCreateStore()

/** Координаты по умолчанию — центр Обнинска: их достаточно поправить под точку. */
const OBNINSK = { lat: 55.0968, lon: 36.6103 }

const roadOptions: Array<{ title: string; value: RoadType }> = [
  { title: 'Асфальт', value: 'asphalt' },
  { title: 'Грунтовка', value: 'dirt' },
]

const name = ref('')
const address = ref('')
const roadType = ref<RoadType>('asphalt')
const lat = ref(OBNINSK.lat)
const lon = ref(OBNINSK.lon)
const submitting = ref(false)
const error = ref<string | null>(null)

const valid = computed(
  () =>
    name.value.trim().length > 0 &&
    Number.isFinite(lat.value) &&
    Number.isFinite(lon.value) &&
    Math.abs(lat.value) <= 90 &&
    Math.abs(lon.value) <= 180,
)

watch(open, (isOpen) => {
  if (isOpen) error.value = null
})

async function submit(): Promise<void> {
  if (!valid.value || submitting.value) return
  submitting.value = true
  error.value = null
  const ok = await erpCreate.addClient({
    name: name.value.trim(),
    address: address.value.trim(),
    road_type: roadType.value,
    lat: lat.value,
    lon: lon.value,
  })
  submitting.value = false
  if (!ok) {
    error.value = 'Магазин не добавлен: проверьте название и координаты.'
    return
  }
  open.value = false
  name.value = ''
  address.value = ''
}
</script>

<style scoped lang="scss">
.coord-row {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 10px;
}
</style>

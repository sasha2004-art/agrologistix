<template>
  <div class="editable-number" @focusout="commit" @keydown.enter="commit" @keydown.esc="reset">
    <v-text-field
      :model-value="draft"
      type="number"
      density="compact"
      variant="outlined"
      hide-details
      :min="min"
      :max="max"
      :step="step"
      :suffix="suffix"
      :disabled="disabled"
      :readonly="loading"
      :aria-label="ariaLabel"
      @update:model-value="onInput"
    >
      <template v-if="loading" #append-inner>
        <v-progress-circular indeterminate size="16" width="2" color="primary" />
      </template>
    </v-text-field>
  </div>
</template>

<script setup lang="ts">
import { ref, watch } from 'vue'

const props = withDefaults(
  defineProps<{
    modelValue: number
    min?: number
    max?: number
    step?: number
    suffix?: string
    loading?: boolean
    disabled?: boolean
    ariaLabel?: string
  }>(),
  {
    step: 1,
    ariaLabel: 'Числовое значение',
    min: undefined,
    max: undefined,
    suffix: '',
    loading: false,
    disabled: false,
  },
)

const emit = defineEmits<{ commit: [value: number] }>()

const draft = ref(String(props.modelValue))

watch(
  () => props.modelValue,
  (value) => {
    draft.value = String(value)
  },
)

// Когда мутация завершилась (успешно или с ошибкой), показываем серверное значение:
// несохранённый ввод не должен оставаться на экране.
watch(
  () => props.loading,
  (loading, wasLoading) => {
    if (wasLoading && !loading) draft.value = String(props.modelValue)
  },
)

function onInput(value: string | number | null): void {
  draft.value = value === null ? '' : String(value)
}

function parseDraft(): number | null {
  const parsed = Number(draft.value.replace(',', '.'))
  if (!Number.isFinite(parsed)) return null
  if (props.min !== undefined && parsed < props.min) return null
  if (props.max !== undefined && parsed > props.max) return null
  return parsed
}

/** Сохраняем только валидное и изменённое значение; иначе возвращаем исходное. */
function commit(): void {
  const parsed = parseDraft()
  if (parsed === null) {
    reset()
    return
  }
  if (parsed === props.modelValue) return
  emit('commit', parsed)
}

function reset(): void {
  draft.value = String(props.modelValue)
}
</script>

<style scoped lang="scss">
.editable-number {
  width: 150px;
}

.editable-number :deep(input) {
  text-align: right;
  font-family: var(--font-mono);
  /* Нативные спиннеры съедают ширину и обрезают значение. */
  appearance: textfield;
  -moz-appearance: textfield;
}

.editable-number :deep(input::-webkit-outer-spin-button),
.editable-number :deep(input::-webkit-inner-spin-button) {
  appearance: none;
  margin: 0;
}

/* Вдавленное поле ввода — согласовано с неоморфной темой. */
.editable-number :deep(.v-field) {
  border-radius: var(--neu-radius-sm);
}

/* У outlined-поля уже есть своя рамка, поэтому кольцо фокуса рисуем по её
   контуру. Глобальный :focus-visible на внутреннем <input> давал второе кольцо
   со сдвигом внутрь поля — мимо рамки, поверх текста и за границей ячейки. */
.editable-number :deep(.v-field__input:focus-visible) {
  outline: none;
}

/* Vuetify сам ставит v-field--focused и для клавиатуры, и для мыши,
   так что состояние фокуса читается одинаково. */
.editable-number :deep(.v-field--focused) {
  outline: 2px solid #6d28d9;
  outline-offset: -2px;
}
</style>

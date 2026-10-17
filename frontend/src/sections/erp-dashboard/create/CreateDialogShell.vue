<template>
  <v-dialog v-model="open" max-width="560" scrollable>
    <v-card class="create-card">
      <v-card-title class="create-title">{{ title }}</v-card-title>
      <v-card-subtitle v-if="subtitle" class="create-subtitle">{{ subtitle }}</v-card-subtitle>

      <v-card-text>
        <form class="create-form" @submit.prevent="emit('submit')">
          <slot />
        </form>
        <v-alert v-if="error" type="error" variant="tonal" density="comfortable" class="mt-3">
          {{ error }}
        </v-alert>
      </v-card-text>

      <v-card-actions class="create-actions">
        <v-spacer />
        <v-btn variant="text" @click="open = false">Отмена</v-btn>
        <v-btn
          color="primary"
          class="btn-gradient"
          :loading="submitting"
          :disabled="submitting"
          @click="emit('submit')"
        >
          {{ submitLabel }}
        </v-btn>
      </v-card-actions>
    </v-card>
  </v-dialog>
</template>

<script setup lang="ts">
/** Общий каркас форм создания: заголовок, слот полей, ошибка и кнопки. */
const open = defineModel<boolean>({ default: false })

withDefaults(
  defineProps<{
    title: string
    subtitle?: string
    submitting?: boolean
    error?: string | null
    submitLabel?: string
  }>(),
  { subtitle: '', submitting: false, error: null, submitLabel: 'Добавить' },
)

const emit = defineEmits<{ submit: [] }>()
</script>

<style scoped lang="scss">
.create-card {
  background: var(--neu-bg);
}

.create-title {
  font-size: 17px;
}

.create-subtitle {
  font-size: 12px;
  color: #5b5175;
}

.create-form {
  display: grid;
  gap: 10px;
  padding-top: 6px;
}

.create-actions {
  padding: 8px 16px 14px;
}
</style>
